import hashlib
import logging
import os
import re
import uuid
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import asyncpg
from groq import (
    APIConnectionError as GroqConnectionError,
    APIError as GroqAPIError,
    InternalServerError as GroqInternalServerError,
    RateLimitError as GroqRateLimitError,
)
from langchain.chat_models import init_chat_model
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from shared.contracts.schema import MemoryExtraction as Mem0Extraction
from shared.embeddings import embeddings

from ..core.config import DATABASE_URL

logger = logging.getLogger(__name__)

MEMORY_STATS = defaultdict(int)


def memory_mode() -> str | None:
    return os.getenv("MEMORY_MODE")


# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------

SCHEMA_SQL = """
CREATE EXTENSION IF NOT EXISTS vector;
CREATE SCHEMA IF NOT EXISTS memory;
CREATE TABLE IF NOT EXISTS memory.conversation_memories (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id        text NOT NULL,
    run_id         text NOT NULL,
    text           text NOT NULL,
    hash           text NOT NULL,
    embedding      vector(1536) NOT NULL,
    keywords       tsvector GENERATED ALWAYS AS (to_tsvector('english', regexp_replace(text, '[^A-Za-z0-9]+', ' ', 'g'))) STORED,
    linked_ids     uuid[] NOT NULL DEFAULT '{}',
    source_turn_id text,
    created_at     timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (user_id, run_id, hash)
);
CREATE INDEX IF NOT EXISTS cm_scope_idx    ON memory.conversation_memories (user_id, run_id);
CREATE INDEX IF NOT EXISTS cm_keywords_idx ON memory.conversation_memories USING gin (keywords);
"""

SEARCH_SQL = """
SELECT id, text, created_at, linked_ids,
       1 - (embedding <=> ($3::text)::vector) AS semantic,
       CASE WHEN $4 = '' THEN 0
            ELSE ts_rank_cd(keywords, to_tsquery('english', $4))
       END AS keyword
FROM memory.conversation_memories
WHERE user_id = $1 AND run_id = $2
ORDER BY embedding <=> ($3::text)::vector
LIMIT 60
"""

SIMILAR_SQL = """
SELECT id, text, created_at
FROM memory.conversation_memories
WHERE user_id = $1 AND run_id = $2
ORDER BY embedding <=> ($3::text)::vector
LIMIT $4
"""

INSERT_SQL = """
INSERT INTO memory.conversation_memories
    (id, user_id, run_id, text, hash, embedding, linked_ids, source_turn_id)
VALUES ($1, $2, $3, $4, $5, ($6::text)::vector, $7::uuid[], $8)
ON CONFLICT (user_id, run_id, hash) DO NOTHING
"""

LINKED_SQL = """
SELECT id, text, created_at, linked_ids
FROM memory.conversation_memories
WHERE user_id = $1 AND run_id = $2
  AND (id = ANY($3::uuid[]) OR linked_ids && $4::uuid[])
"""

ALL_SQL = """
SELECT id, text, linked_ids, source_turn_id, created_at
FROM memory.conversation_memories
WHERE user_id = $1 AND run_id = $2
ORDER BY created_at
"""


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

async def get_connection():
    return await asyncpg.connect(DATABASE_URL)


@asynccontextmanager
async def database():
    db = await get_connection()
    try:
        yield db
    finally:
        await db.close()


async def ensure_schema() -> None:
    """Create the conversation-memory table and indexes if missing. Safe to run on every startup."""
    async with database() as db:
        await db.execute(SCHEMA_SQL)


def to_dicts(rows) -> list[dict]:
    dicts = []
    for row in rows:
        dicts.append(dict(row))
    return dicts


def to_vector_literal(vector: list[float]) -> str:
    values = []
    for value in vector:
        values.append(f"{value:.7f}")
    return "[" + ",".join(values) + "]"


def memory_hash(text: str) -> str:
    normalized = " ".join(text.lower().split())
    return hashlib.md5(normalized.encode()).hexdigest()


async def similar_memories(db, user_id, run_id, query_vec, limit=10) -> list[dict]:
    rows = await db.fetch(SIMILAR_SQL, user_id, run_id, to_vector_literal(query_vec), limit)
    return to_dicts(rows)


async def linked_memories(db, user_id, run_id, ids: list[str], recalled: list[str]) -> list[dict]:
    """Stored memories with one of these ids, or that link to one of the recalled ids. This user and run only."""
    rows = await db.fetch(LINKED_SQL, user_id, run_id, ids, recalled)
    return to_dicts(rows)


async def all_memories(db, user_id, run_id) -> list[dict]:
    rows = await db.fetch(ALL_SQL, user_id, run_id)
    return to_dicts(rows)


async def insert_memory(db, user_id, run_id, text, vec, linked_ids, turn_id) -> bool:
    status = await db.execute(
        INSERT_SQL,
        uuid.uuid4(),
        user_id,
        run_id,
        text,
        memory_hash(text),
        to_vector_literal(vec),
        linked_ids,
        turn_id,
    )
    return status.endswith(" 1")


# ---------------------------------------------------------------------------
# Links between memories
# ---------------------------------------------------------------------------

def linked_ids_of(row: dict) -> list[str]:
    linked_ids = []
    for target in row.get("linked_ids") or []:
        linked_ids.append(str(target))
    return linked_ids


def current_memories(rows: list[dict]) -> list[dict]:
    """Drop every memory that a newer memory in the list links to (i.e. corrects or changes). Order is kept."""
    created_at = {}
    for row in rows:
        created_at[str(row["id"])] = row["created_at"]

    replaced = set()
    for row in rows:
        for target in linked_ids_of(row):
            if target in created_at and row["created_at"] > created_at[target]:
                replaced.add(target)

    current = []
    for row in rows:
        if str(row["id"]) not in replaced:
            current.append(row)
    return current


async def with_linked(fetch, rows: list[dict], max_rounds: int = 3) -> list[dict]:
    """Add the memories connected to these rows by a link, in both directions: the older ones they correct,
    and the newer ones that correct them (so a stale memory is not shown as current just because its
    correction scored lower). A correction can itself be corrected, so this repeats, at most max_rounds times.

    fetch(ids, recalled) is an async function returning the stored rows whose id is in ids or that link to
    one of the recalled ids.
    """
    rows = list(rows)
    if not rows:
        return rows

    for _ in range(max_rounds):
        known_ids = set()
        linked_ids = set()
        for row in rows:
            known_ids.add(str(row["id"]))
            linked_ids.update(linked_ids_of(row))
        missing_ids = sorted(linked_ids - known_ids)

        fetched = await fetch(missing_ids, sorted(known_ids))
        new_rows = []
        for row in fetched:
            if str(row["id"]) not in known_ids:
                new_rows.append(dict(row))
        if not new_rows:
            break
        rows += new_rows
    return rows


def valid_links(existing: list[dict], linked_ids: list, new_created_at) -> tuple[list[str], list[str]]:
    """Split linked_ids into (valid, dropped). A link is valid only if it points at an existing memory that is
    older than the new one. Each valid id appears once."""
    older_ids = set()
    for memory in existing:
        if memory["created_at"] < new_created_at:
            older_ids.add(str(memory["id"]))

    valid, dropped = [], []
    for link in map(str, linked_ids):
        if link not in older_ids:
            dropped.append(link)
        elif link not in valid:
            valid.append(link)
    return valid, dropped


def attach_earlier(current: list[dict], everything: list[dict]) -> list[dict]:
    """Give each current memory an "earlier" list: the texts of the memories it links to, when we have them."""
    text_by_id = {}
    for row in everything:
        text_by_id[str(row["id"])] = row["text"]

    with_earlier = []
    for row in current:
        earlier = []
        for target in linked_ids_of(row):
            if target in text_by_id:
                earlier.append(text_by_id[target])
        with_earlier.append({**row, "earlier": earlier})
    return with_earlier


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def render_memory_line(number: int, row: dict) -> str:
    earlier = f" (earlier: {'; '.join(row['earlier'])})" if row.get("earlier") else ""
    return f"{number}. {row['text']}{earlier}"


def render_memories(rows: list[dict]) -> str:
    if not rows:
        return ""
    lines = []
    for number, row in enumerate(rows, 1):
        lines.append(render_memory_line(number, row))
    memory_block = "\n".join(lines)

    return (
        "Memories from this conversation, oldest first. If two memories disagree, "
        f"the later one is current:\n{memory_block}"
    )


def recent_text(messages, max_items: int = 6) -> str:
    """The last few turns BEFORE the newest user message, oldest first.

    The newest user message is passed to the extractor separately, and the answer to it is
    not context for understanding it, so both are left out.
    """
    newest_human = len(messages)
    for i, message in enumerate(messages):
        if isinstance(message, HumanMessage):
            newest_human = i

    turns = []
    for message in messages[:newest_human]:
        if isinstance(message, HumanMessage):
            turns.append(f"User: {message.content}")
        elif isinstance(message, AIMessage) and message.content and not getattr(message, "tool_calls", None):
            turns.append(f"Assistant: {message.content}")
    return "\n".join(turns[-max_items:])


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

memory_extraction_llm_mem0 = (
    init_chat_model(
        model="groq:openai/gpt-oss-120b",
        temperature=0,
        streaming=False,
        reasoning_effort="low",
    )
    .with_structured_output(Mem0Extraction, method="function_calling")
    .with_config(tags=["fetching_memory"])
    .with_retry(
        stop_after_attempt=2,
        retry_if_exception_type=(GroqConnectionError, GroqInternalServerError, GroqRateLimitError),
    )
)

MEMORY_EXTRACTION_PROMPT = """You keep the memory of an HR assistant for one conversation. Read the user's new
message and write down each fact about the user's own situation that the assistant
may need later in this conversation.

Write each memory as one self-contained sentence that starts with "User" and makes
sense without the conversation: "User applied for sick leave from 3 March to 7 March",
not "from 3 to 7".

Rules:
1. Record only what the user states about their own situation in the new message.
   Use the recent conversation only to understand what the message refers to.
2. Copy names, IDs, dates and amounts exactly as the user wrote them. Never round,
   convert or guess a value.
3. Do not record questions, requests for information, company policy, amounts quoted
   from policy, or facts about other people.
4. If the message changes, corrects or cancels something in Existing memories, write
   it as a change that names the old and the new value, and put that memory's number
   in "linked". Example: "User corrected the medical claim amount from 15,000 to 12,500".
5. If the message only repeats something already in Existing memories, return nothing
   for it.
6. If nothing qualifies, return {"memories": []}.

Example
Existing memories:
[0] User filed a medical claim for 15,000
New message: "Sorry, the medical claim is 12,500, not 15,000."
Output: {"memories": [{"text": "User corrected the medical claim amount from 15,000 to 12,500", "linked": ["0"]}]}

Example
New message: "My colleague's ticket SR-90011 is also open. What is the claim limit?"
Output: {"memories": []}"""


def build_extraction_messages(existing: list[dict], recent: str, message: str) -> list:
    existing_lines = []
    for i, memory in enumerate(existing):
        existing_lines.append(f"[{i}] {memory['text']}")
    existing_block = "\n".join(existing_lines) or "(none)"

    return [
        SystemMessage(content=MEMORY_EXTRACTION_PROMPT),
        HumanMessage(content=(
            f"Existing memories:\n{existing_block}\n\n"
            f"Recent conversation:\n{recent or '(none)'}\n\n"
            f"New message: {message}"
        )),
    ]


def resolve_link_refs(refs: list, existing: list[dict]) -> tuple[list[str], list]:
    linked_ids = []
    bad_links = []
    for ref in refs:
        try:
            index = int(str(ref).strip("[] "))
        except ValueError:
            index = -1

        if not 0 <= index < len(existing):
            logger.warning("Ignoring invalid memory link %r (have %d existing memories)", ref, len(existing))
            bad_links.append(ref)
            continue

        memory_id = str(existing[index]["id"])
        if memory_id not in linked_ids:
            linked_ids.append(memory_id)
    return linked_ids, bad_links


async def extract_relevant_info(existing: list[dict], recent: str, message: str) -> list[dict]:
    """Turn the user's new message into new memories.

    existing: nearby stored memories, each {"id", "text"} (e.g. from similar_memories).
    recent:   a short text rendering of the last few turns, for context only.
    message:  the user's new message.
    Returns [{"text": str, "linked_ids": [memory id, ...], "bad_links": [ref, ...]}], or [] if nothing
    qualifies or the call fails. "bad_links" holds the link references the model gave that did not
    point at any existing memory (not a number, or out of range); they are not in "linked_ids".
    """
    try:
        result = await memory_extraction_llm_mem0.ainvoke(
            build_extraction_messages(existing, recent, message))
    except GroqAPIError as e:
        logger.warning("Memory extraction skipped (%s: %s). Last user message: %r",
                       type(e).__name__, getattr(e, "code", None) or str(e)[:120], message)
        return []
    except Exception:
        logger.exception("Memory extraction failed. Last user message: %r", message)
        return []

    new_memories = []
    for memory in result.memories:
        text = memory.text.strip()
        if not text:
            continue
        linked_ids, bad_links = resolve_link_refs(memory.linked, existing)
        new_memories.append({"text": text, "linked_ids": linked_ids, "bad_links": bad_links})
    return new_memories


# ---------------------------------------------------------------------------
# Grounding check
# ---------------------------------------------------------------------------

TOKEN_PUNCTUATION = ".,;:!?()\"'₹$"


def clean_token(token: str) -> str:
    return token.strip(TOKEN_PUNCTUATION).lower()


def has_digit(token: str) -> bool:
    for char in token:
        if char.isdigit():
            return True
    return False


def digit_tokens(text: str) -> set[str]:
    tokens = set()
    for word in text.split():
        token = clean_token(word)
        if has_digit(token):
            tokens.add(token)
    return tokens


def is_grounded(note_text: str, sources: list[str]) -> bool:
    """True if every number/ID token in the note appears as a whole token in a source."""
    allowed: set[str] = set()
    for source in sources:
        allowed |= digit_tokens(source)
    return digit_tokens(note_text) <= allowed


# ---------------------------------------------------------------------------
# Adding memories
# ---------------------------------------------------------------------------

def drop_invalid_links(new_memories: list[dict], existing: list[dict]) -> None:
    now = datetime.now(timezone.utc)
    for memory in new_memories:
        memory["linked_ids"], dropped = valid_links(existing, memory["linked_ids"], now)
        if dropped:
            logger.warning("Dropped invalid memory links %s for %r", dropped, memory["text"])
            memory["bad_links"] += dropped


def select_grounded(new_memories: list[dict], sources: list[str]) -> list[dict]:
    grounded = []
    for memory in new_memories:
        if is_grounded(memory["text"], sources):
            grounded.append(memory)
        else:
            memory["status"] = "ungrounded"
    return grounded


async def store_memories(user_id: str, run_id: str, memories: list[dict], turn_id: str | None) -> None:
    texts = []
    for memory in memories:
        texts.append(memory["text"])

    vectors = await embeddings.aembed_documents(texts)
    async with database() as db:
        async with db.transaction():
            for memory, vector in zip(memories, vectors):
                inserted = await insert_memory(
                    db, user_id, run_id, memory["text"], vector, memory["linked_ids"], turn_id)
                memory["status"] = "added" if inserted else "duplicate"


async def add_memories(user_id: str, run_id: str, message: str, recent: str = "",
                       turn_id: str | None = None) -> list[dict]:
    """Extract memories from the user's new message and store the new ones.

    Returns one dict per extracted memory: {"text", "linked_ids", "bad_links", "status"} where
    status is "added", "duplicate" or "ungrounded". Raises on failure (LLM, embedding, database);
    the memory_add node catches, logs and counts it, so a failed add never breaks an answer.
    """
    query_vec = await embeddings.aembed_query(message)
    async with database() as db:
        existing = await similar_memories(db, user_id, run_id, query_vec)

    new_memories = await extract_relevant_info(existing, recent, message)
    if not new_memories:
        return []

    drop_invalid_links(new_memories, existing)

    sources = [message]
    for memory in existing:
        sources.append(memory["text"])
    grounded = select_grounded(new_memories, sources)
    if grounded:
        await store_memories(user_id, run_id, grounded, turn_id)
    return new_memories


# ---------------------------------------------------------------------------
# Searching memories
# ---------------------------------------------------------------------------

def to_keyword_query(query: str) -> str:
    words = re.findall(r"[a-z0-9]+", query.lower())
    return " | ".join(words)


def score_rows(rows: list[dict]) -> None:
    max_keyword = 0.0
    for row in rows:
        max_keyword = max(max_keyword, row["keyword"])

    for row in rows:
        if max_keyword > 0:
            row["keyword_norm"] = row["keyword"] / max_keyword
            row["score"] = (row["semantic"] + row["keyword_norm"]) / 2
        else:
            row["keyword_norm"] = 0.0
            row["score"] = row["semantic"]


async def search_memories(user_id: str, run_id: str, query: str,
                          top_k: int = 10, threshold: float = 0.1) -> list[dict]:
    keyword_query = to_keyword_query(query)
    query_vec = await embeddings.aembed_query(query)

    async with database() as db:
        rows = await db.fetch(SEARCH_SQL, user_id, run_id, to_vector_literal(query_vec), keyword_query)
        candidates = []
        for row in rows:
            if row["semantic"] >= threshold:
                candidates.append(dict(row))
        score_rows(candidates)
        top = sorted(candidates, key=lambda row: row["score"], reverse=True)[:top_k]

        async def fetch_linked(ids, recalled):
            return await linked_memories(db, user_id, run_id, ids, recalled)

        everything = await with_linked(fetch_linked, top)

    current = attach_earlier(current_memories(everything), everything)
    return sorted(current, key=lambda row: row["created_at"])
