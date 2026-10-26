from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
import os
import asyncpg
from ..core.config import DATABASE_URL


async def get_connection():
    return await asyncpg.connect(DATABASE_URL)
# Env values are strings (or None when unset), so convert them and keep defaults.
SUMMARIZE_THRESHOLD = int(os.getenv("SUMMARIZE_THRESHOLD", "12"))
KEEP_RAW_TURNS = int(os.getenv("KEEP_RAW_TURNS", "5"))
LEDGER_LABEL="[Conversation notes]"
SUMMARY_PROMPT = (
    """You maintain a running notes ledger for a conversation.

You get EXISTING NOTES (may be empty) and NEW MESSAGES.
Return the updated notes.

Rules:
1. Copy every line of EXISTING NOTES forward unchanged, unless a new message
   explicitly corrects or replaces it. Never shorten or merge existing lines.
2. Add one line per new item from NEW MESSAGES.
3. Keep identifiers exactly as written: names, numbers, ticket or claim IDs,
   dates, amounts, seat and office locations. Do not paraphrase them.
4. Record what the user asked, what the assistant answered, and what is unresolved.
5. No commentary. Use exactly these sections:

FACTS:
DECISIONS:
IDENTIFIERS AND DATES:
OPEN QUESTIONS:"""
)

def is_ledger(message)-> bool:
       return isinstance(message, SystemMessage) and str(message.content).startswith(LEDGER_LABEL)

def ledger_text(message)->str:
       return str(message.content[len(LEDGER_LABEL):]).strip()

def render(message)->str:
       lines= []
       for m in message:
              if isinstance(m,HumanMessage):
                     lines.append(f"User: {m.content}")
              elif isinstance(m,AIMessage) and m.content and not getattr(m,"tool_calls",None):
                    lines.append(f"Assisstant: {m.content}") 
       return "\n".join(lines)

import re

IDENTIFIER_PATTERN = re.compile(r"\b[\w-]*\d[\w-]*\b")


def missing_identifiers(old_notes: str, new_notes: str) -> list[str]:
    old_ids = set(IDENTIFIER_PATTERN.findall(old_notes))
    return sorted(i for i in old_ids if i not in new_notes)


def ledger_first(messages):
     ledger = [m for m in messages if is_ledger(m)]
     rest = [m for m in messages if not is_ledger(m)]
     return ledger[-1:] +rest

def guard_notes(old_notes: str, new_notes: str) -> tuple[str, list[str]]:
    missing = missing_identifiers(old_notes, new_notes)
    if not missing:
        return new_notes, []
    recovered = [line for line in old_notes.splitlines() if any(i in line for i in missing)]
    return new_notes + "\n\nRECOVERED:\n" + "\n".join(recovered), missing

def split_for_summary(messages):
    human_turns = [m for m in messages if isinstance(m, HumanMessage)]
    if len(human_turns) <= SUMMARIZE_THRESHOLD:
        return None
    cut = messages.index(human_turns[-KEEP_RAW_TURNS])
    ledger = next((m for m in messages if is_ledger(m)), None)
    to_compress = [m for m in messages[:cut] if not is_ledger(m)]
    to_remove = to_compress + ([ledger] if ledger else [])
    return ledger, to_compress, to_remove

async def summarize(llm,old_ledger, new_messages, prompt=SUMMARY_PROMPT) -> str:
    human = HumanMessage(content=f"EXISTING NOTES: \n{old_ledger or '(empty)'}\n\n New Messages:\n{render(new_messages)}")
    result = await llm.ainvoke([SystemMessage(content=prompt), human])
    return result.content

NON_ALNUM_PATTERN = re.compile(r"[\W_]+")


def normalize_value(value: str) -> str:
    return NON_ALNUM_PATTERN.sub("", str(value).casefold())

TOKEN_PATTERN = re.compile(r"[^\W_]+")


def tokenize(text) -> list[str]:
    """Split text into lowercase alphanumeric words: 'B-14, Pune' -> ['b', '14', 'pune']."""
    return TOKEN_PATTERN.findall(str(text).casefold())


def contains_value(haystack, needle) -> bool:
    """True if the words of `needle` appear in `haystack` as a consecutive run.

    Both sides are split into tokens first, so case and punctuation are ignored
    and whole words must match: 'B-14' is found in 'seat b 14 please' but not in
    'seat B-140'. Word order matters ('Rao Priya' does not match 'Priya Rao').
    """
    needle_tokens = tokenize(needle)
    if not needle_tokens:
        return False
    hay_tokens = tokenize(haystack)
    n = len(needle_tokens)
    return any(hay_tokens[i:i + n] == needle_tokens for i in range(len(hay_tokens) - n + 1))

async def apply_fact(thread_id, slot, value, turn_id, source_text="", retracts=False):
    value_norm = normalize_value(value)
    db = await get_connection()
    try:
        async with db.transaction():
            await db.execute("SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                         f"{thread_id}:{slot}")
            rows = await db.fetch(
                'SELECT id, value_norm, version, superseded_by, retracted FROM "ThreadFacts" '
                'WHERE thread_id=$1 AND slot=$2 FOR UPDATE', thread_id, slot)
            next_version = max((r["version"] for r in rows), default=0) + 1
            current = next(
                (r for r in rows if r["superseded_by"] is None and not r["retracted"]), None)

            if not normalize_value(value) and not retracts:
                 return "rejected"

            if retracts:
                if current is None:
                    return "no-op"
                if not normalize_value(value) or value_norm == current["value_norm"]:
                    await db.execute(
                        'UPDATE "ThreadFacts" SET retracted=TRUE WHERE id=$1', current["id"])
                    return "retracted"
                return "no-op"

            if current is not None and current["value_norm"] == value_norm:
                return "no-op"

            new_id = await db.fetchval(
                'INSERT INTO "ThreadFacts" '
                '(thread_id, slot, value, value_norm, version, source_turn_id, source_text, retracted) '
                'VALUES ($1,$2,$3,$4,$5,$6,$7,FALSE) RETURNING id',
                thread_id, slot, value, value_norm, next_version, turn_id, source_text)

            if current is None:
                return "added"

            await db.execute(
                'UPDATE "ThreadFacts" SET superseded_by=$1 WHERE id=$2',
                new_id, current["id"])
            return "updated"
    finally:
        await db.close()

async def fetch_thread_data(thread_id) -> str:
    """Current facts for a thread as prompt-ready lines ('- seat: B-14'), or 'none'."""
    db = await get_connection()
    try:
        rows = await db.fetch(
            'SELECT slot, value FROM "ThreadFacts" '
            'WHERE thread_id=$1 AND superseded_by IS NULL AND retracted=FALSE ORDER BY slot',
            thread_id)
    finally:
        await db.close()
    return "\n".join(f"- {r['slot']}: {r['value']}" for r in rows) or "none"