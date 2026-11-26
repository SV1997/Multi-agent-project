"""The keyword index is read, changed and written back under a per-namespace advisory lock.

Run from services/ingestion_service:  python -m pytest tests/test_bm25_lock.py
The tests marked `needs_db` are skipped unless DATABASE_URL is exported in the shell (a value that only comes from
.env does not count) and points at a database with the bm25_indexes table. They only touch rows of throwaway namespaces ("test-bm25-...") and delete them afterwards.
"""
import asyncio
import contextlib
import os
import sys
import types
import uuid

import pytest
from fastapi import HTTPException
from langchain_core.documents import Document

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))
fake_emb = types.ModuleType("shared.embeddings.embeddings")
fake_emb.embeddings = object()
sys.modules.setdefault("shared.embeddings.embeddings", fake_emb)

from app.api import route  # noqa: E402
from conftest import EXPLICIT_DATABASE_URL  # noqa: E402

pytestmark = pytest.mark.real_bm25_lock
needs_db = pytest.mark.skipif(not EXPLICIT_DATABASE_URL, reason="DATABASE_URL is not exported")


# ---------------------------------------------------------------- with a fake connection

class FakeConnection:
    def __init__(self):
        self.events: list = []

    @contextlib.asynccontextmanager
    async def transaction(self):
        self.events.append("begin")
        try:
            yield
        except BaseException:
            self.events.append("rollback")
            raise
        self.events.append("commit")

    async def execute(self, query, *args):
        self.events.append((query, args))

    async def close(self):
        self.events.append("close")


@pytest.fixture
def connection(monkeypatch):
    conn = FakeConnection()

    async def connect():
        return conn

    monkeypatch.setattr(route, "get_connection", connect)
    return conn


def test_the_lock_is_taken_before_the_body_runs(connection):
    async def run():
        async with route.bm25_lock("hr"):
            connection.events.append("body")

    asyncio.run(run())
    assert connection.events == [
        "begin",
        ("SET LOCAL lock_timeout = '30s'", ()),
        ("SELECT pg_advisory_xact_lock(hashtextextended($1, 0))", ("bm25:hr",)),
        "body",
        "commit",
        "close",
    ]


def test_an_error_in_the_body_propagates_and_the_connection_is_closed(connection):
    async def run():
        async with route.bm25_lock("legal"):
            raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        asyncio.run(run())
    assert connection.events[-2:] == ["rollback", "close"]


# ---------------------------------------------------------------- against a real database

@pytest.fixture
def namespace():
    name = f"test-bm25-{uuid.uuid4().hex}"
    yield name
    asyncio.run(route.delete_bm25_index(name))


async def add_chunk(namespace: str, text: str, lock):
    async with lock(namespace):
        data = await route.load_bm25_index(namespace)
        await asyncio.sleep(0.2)
        chunks = (data["chunks"] if data else []) + [{"text": text}]
        await route.save_bm25_index(namespace, {"chunks": chunks})


async def two_writers(namespace: str, lock) -> list[str]:
    await asyncio.gather(add_chunk(namespace, "first", lock), add_chunk(namespace, "second", lock))
    return sorted(c["text"] for c in (await route.load_bm25_index(namespace))["chunks"])


@needs_db
def test_two_concurrent_writers_keep_both_chunks(namespace):
    assert asyncio.run(two_writers(namespace, route.bm25_lock)) == ["first", "second"]


@needs_db
def test_without_the_lock_one_chunk_is_lost(namespace):
    """Documents the bug the lock fixes."""
    assert len(asyncio.run(two_writers(namespace, lambda _: contextlib.nullcontext()))) == 1


class ShortTimeout:
    """A real connection with the 30s lock timeout cut to 500ms, so the test does not take half a minute."""

    def __init__(self, conn):
        self.conn = conn

    def __getattr__(self, name):
        return getattr(self.conn, name)

    async def execute(self, query, *args):
        return await self.conn.execute(query.replace("'30s'", "'500ms'"), *args)


@pytest.fixture
def short_timeout(monkeypatch):
    real = route.get_connection

    async def connect():
        return ShortTimeout(await real())

    monkeypatch.setattr(route, "get_connection", connect)


@needs_db
def test_waiting_longer_than_lock_timeout_raises(namespace, short_timeout):
    import asyncpg

    async def run():
        async with route.bm25_lock(namespace):
            async with route.bm25_lock(namespace):   # second connection, so it has to wait
                pytest.fail("the second holder got the lock")

    with pytest.raises(asyncpg.LockNotAvailableError):
        asyncio.run(asyncio.wait_for(run(), timeout=10))


@needs_db
def test_another_namespace_is_not_blocked(namespace, short_timeout):
    async def run():
        async with route.bm25_lock(namespace):
            async with route.bm25_lock(namespace + "-other"):
                return True

    assert asyncio.run(run())


@needs_db
def test_ingest_answers_500_when_the_lock_cannot_be_had(monkeypatch, short_timeout):
    monkeypatch.setattr(route, "load_taxonomy_or_warn", lambda warnings: None)
    monkeypatch.setattr(route, "load_document",
                        lambda source, source_type: [Document(page_content="leave policy text " * 20, metadata={})])
    monkeypatch.setattr(route, "upsert_document", lambda chunk, *a, **k: len(chunk))
    saved = []

    async def save(*args):
        saved.append(args)

    monkeypatch.setattr(route, "save_bm25_index", save)
    request = route.IngestionRequest(namespace="hr", source=[{"path": "a.md", "type": "markdown"}])

    async def run():
        async with route.bm25_lock("hr"):
            await route.ingest(request)

    with pytest.raises(HTTPException) as error:
        asyncio.run(asyncio.wait_for(run(), timeout=10))
    assert error.value.status_code == 500 and error.value.detail.startswith("Ingestion failed")
    assert "lock timeout" in error.value.detail and not saved
