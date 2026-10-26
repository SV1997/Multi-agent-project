from .context_policy import get_connection
import hashlib
import uuid
import asyncpg
from ..core.config import DATABASE_URL
from shared.embeddings import embeddings
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
from langchain.chat_models import init_chat_model
from groq import (
    APIConnectionError as GroqConnectionError,
    APIError as GroqAPIError,
    InternalServerError as GroqInternalServerError,
    RateLimitError as GroqRateLimitError,
)
from shared.contracts.schema import HR_SLOTS, Extraction, Fact, MemoryExtraction as Mem0Extraction
import logging
logger = logging.getLogger(__name__)
import re
import os
from collections import defaultdict
def memory_mode()->str:
     return os.getenv("MEMORY_MODE")
MEMORY_STATS = defaultdict(int)
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
SEARCH_SQL="""
SELECT id, text, created_at, linked_ids,
1 - (embedding<=>($3::text)::vector) AS semantic,
CASE WHEN $4 = '' THEN 0
ELSE ts_rank_cd(keywords, to_tsquery('english', $4)) END           AS keyword
FROM memory.conversation_memories
WHERE user_id = $1 AND run_id = $2
ORDER BY embedding <=> ($3::text)::vector
LIMIT 60

"""

# Strict json_schema decoding sometimes makes gpt-oss write its reasoning ("no new fact, so empty")
# instead of {"memories": []}, which Groq rejects as output_parse_failed. The tool-calling path
# did not show that failure in the classifier tests, so it is used here too.
# Only transient errors are retried: a parse failure repeats identically and every retry costs tokens.
memory_extraction_llm_mem0 = (init_chat_model(model="groq:openai/gpt-oss-120b", temperature=0, streaming=False, reasoning_effort="low").
        with_structured_output(Mem0Extraction, method="function_calling")
        .with_config(tags=["fetching_memory"])
        .with_retry(
            stop_after_attempt=2,
            retry_if_exception_type=(GroqConnectionError, GroqInternalServerError, GroqRateLimitError),
        )
        )


async def get_connection():
    return await asyncpg.connect(DATABASE_URL)

async def ensure_schema() -> None:
    """Create the conversation-memory table and indexes if missing. Safe to run on every startup."""
    db = await get_connection()
    try:
        await db.execute(SCHEMA_SQL)
    finally:
        await db.close()

def to_vector_literal(v: list[float]) -> str:
    return "[" + ",".join(f"{x:.7f}" for x in v) + "]"

async def similar_memories(db, user_id, run_id, query_vec, limit=10) -> list[dict]:
    rows = await db.fetch("""
    SELECT id, text, created_at FROM memory.conversation_memories
    WHERE user_id=$1 AND run_id=$2
    ORDER BY embedding <=> ($3::text)::vector
    LIMIT $4
""", user_id, run_id, to_vector_literal(query_vec), limit)
    return [dict(r) for r in rows]
    
def render_memories(rows: list[dict]) -> str:
    if not rows:
         return ""
    lines = "\n".join(f"{i}. {row["text"]}" for i,row in enumerate(rows,1))
    return ("Memories from this conversation, oldest first. If two memories disagree, "
            f"the later one is current:\n{lines}")
async def insert_memory(db, user_id, run_id, text, vec, linked_ids, turn_id) -> bool:
    status = await db.execute("""
    INSERT INTO  memory.conversation_memories (id, user_id, run_id, text, hash, embedding, linked_ids, source_turn_id)
           VALUES ($1, $2, $3, $4, $5, ($6::text)::vector, $7::uuid[], $8)
           ON CONFLICT (user_id, run_id, hash) DO NOTHING 
""", uuid.uuid4(), user_id, run_id, text,memory_hash(text),to_vector_literal(vec), linked_ids,turn_id)
    return  status.endswith(" 1")

async def all_memories(db, user_id, run_id) -> list[dict]:
     rows = await db.fetch(
        """SELECT id, text, linked_ids, source_turn_id, created_at
           FROM memory.conversation_memories
           WHERE user_id = $1 AND run_id = $2
           ORDER BY created_at""",
        user_id, run_id)
     return [dict(r) for r in rows]

def recent_text(messages, max_items: int = 6) -> str:
    """The last few turns BEFORE the newest user message, oldest first.

    The newest user message is passed to the extractor separately, and the answer to it is
    not context for understanding it, so both are left out.
    """
    last_human = max((i for i, m in enumerate(messages) if isinstance(m, HumanMessage)), default=len(messages))
    turns = []
    for m in messages[:last_human]:
        if isinstance(m, HumanMessage):
            turns.append(f"User: {m.content}")
        elif isinstance(m, AIMessage) and m.content and not getattr(m, "tool_calls", None):
            turns.append(f"Assistant: {m.content}")
    return "\n".join(turns[-max_items:])

def memory_hash(text: str) -> str:
    return hashlib.md5(" ".join(text.lower().split()).encode()).hexdigest()

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


async def extract_relevant_info(existing: list[dict], recent: str, message: str) -> list[dict]:
        """Turn the user's new message into new memories.

        existing: nearby stored memories, each {"id", "text"} (e.g. from similar_memories).
        recent:   a short text rendering of the last few turns, for context only.
        message:  the user's new message.
        Returns [{"text": str, "linked_ids": [memory id, ...], "bad_links": [ref, ...]}], or [] if nothing
        qualifies or the call fails. "bad_links" holds the link references the model gave that did not
        point at any existing memory (not a number, or out of range); they are not in "linked_ids".
        """
        existing_block = "\n".join(f"[{i}] {m['text']}" for i, m in enumerate(existing)) or "(none)"
        try:
            result = await memory_extraction_llm_mem0.ainvoke([
                SystemMessage(content=MEMORY_EXTRACTION_PROMPT),
                HumanMessage(content=(
                    f"Existing memories:\n{existing_block}\n\n"
                    f"Recent conversation:\n{recent or '(none)'}\n\n"
                    f"New message: {message}"
                )),
            ])
        except GroqAPIError as e:
            # Provider-side failure (unparseable output, rate limit, ...): nothing is stored for
            # this turn. Expected often enough that a one-line warning is enough, not a traceback.
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
            # The model refers to existing memories by their [number]; map that back to real ids
            # and ignore anything that isn't a valid number.
            linked_ids = []
            bad_links = []
            for ref in memory.linked:
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
            new_memories.append({"text": text, "linked_ids": linked_ids, "bad_links": bad_links})
            print(new_memories)
        return new_memories
_STRIP = ".,;:!?()\"'₹$"

def _clean(token:str)-> str:
        return token.strip(_STRIP).lower()

def digit_tokens(text:str)-> str:
        return {t for t in (_clean(w) for w in text.split()) if t and any(c.isdigit() for c in t)}

def is_grounded(note_text: str, sources:list[str]) -> bool:
        """True if every number/ID token in the note appears as a whole token in a source."""
        allowed: set[str] = set()
        for s in sources:
            allowed |= digit_tokens(s)
        return digit_tokens(note_text) <= allowed

async def add_memories(user_id: str, run_id: str, message: str, recent: str = "",
                       turn_id: str | None = None) -> list[dict]:
        """Extract memories from the user's new message and store the new ones.

        Returns one dict per extracted memory: {"text", "linked_ids", "bad_links", "status"} where
        status is "added", "duplicate" or "ungrounded". Raises on failure (LLM, embedding, database);
        the memory_add node catches, logs and counts it, so a failed add never breaks an answer.
        """
        query_vec = await embeddings.aembed_query(message)
        db = await get_connection()
        try:
            existing = await similar_memories(db, user_id, run_id, query_vec)
        finally:
            await db.close()

        new_memories = await extract_relevant_info(existing, recent, message)
        if not new_memories:
            return []

        sources = [message] + [m["text"] for m in existing]
        keep = []
        for memory in new_memories:
            if is_grounded(memory["text"], sources):
                keep.append(memory)
            else:
                memory["status"] = "ungrounded"
        if not keep:
            return new_memories

        vectors = await embeddings.aembed_documents([m["text"] for m in keep])
        db = await get_connection()
        try:
            async with db.transaction():
                for memory, vector in zip(keep, vectors):
                    inserted = await insert_memory(
                        db, user_id, run_id, memory["text"], vector, memory["linked_ids"], turn_id)
                    memory["status"] = "added" if inserted else "duplicate"
        finally:
            await db.close()
        return new_memories

async def search_memories(user_id: str, run_id: str, query: str,
                          top_k: int = 10, threshold: float = 0.1) -> list[dict]:
    words = re.findall(r"[a-z0-9]+", query.lower())
    ts_query = " | ".join(words)

    query_vec = await embeddings.aembed_query(query)
    db = await get_connection()
    try:
        rows = await db.fetch(SEARCH_SQL, user_id, run_id, to_vector_literal(query_vec), ts_query)
    finally:
        await db.close()

    rows = [dict(r) for r in rows if r["semantic"] >= threshold]
    kmax = max((r["keyword"] for r in rows), default=0.0)
    for r in rows:
        r["keyword_norm"] = r["keyword"] / kmax if kmax > 0 else 0.0
        r["score"] = (r["semantic"] + r["keyword_norm"]) / 2 if kmax > 0 else r["semantic"]

    top = sorted(rows, key=lambda r: r["score"], reverse=True)[:top_k]
    return sorted(top, key=lambda r: r["created_at"])