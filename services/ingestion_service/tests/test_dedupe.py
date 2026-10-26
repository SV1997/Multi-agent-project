"""Feature 1: deterministic chunk IDs, no duplicates on re-ingest, stale text removed.

Run from services/ingestion_service:  python -m pytest tests/test_dedupe.py
Uses an in-memory fake Pinecone index (serverless semantics: list by prefix, delete by ID).
"""
import os
import sys
import types
from types import SimpleNamespace

import pytest
from langchain_core.documents import Document

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))
fake_emb = types.ModuleType("shared.embeddings.embeddings")
fake_emb.embeddings = object()
sys.modules.setdefault("shared.embeddings.embeddings", fake_emb)

from app.pinecone import upsert as up  # noqa: E402


class FakeIndex:
    def __init__(self, store: dict):
        self.store = store

    def list(self, prefix: str, namespace: str):
        yield [i for i in self.store if i.startswith(prefix)]

    def fetch(self, ids, namespace):
        return SimpleNamespace(vectors={i: SimpleNamespace(metadata=self.store[i]["meta"]) for i in ids if i in self.store})

    def delete(self, ids, namespace):
        for i in ids:
            self.store.pop(i, None)


@pytest.fixture
def store(monkeypatch):
    data: dict = {}
    monkeypatch.setattr(up, "_get_index", lambda: FakeIndex(data))

    def fake_from_documents(documents, ids, **_):
        for i, d in zip(ids, documents):
            data[i] = {"text": d.page_content, "meta": dict(d.metadata)}

    monkeypatch.setattr(up.PineconeVectorStore, "from_documents", staticmethod(fake_from_documents))
    return data


@pytest.fixture(autouse=True)
def restore_route_functions():
    """Some tests below replace functions on the route module by plain assignment. Put the real ones back after
    each test, so a stub can never leak into the tests of other files (they would be testing the stub)."""
    from app.api import route
    names = ("load_bm25_index", "save_bm25_index", "load_document", "upsert_document")
    originals = {name: getattr(route, name) for name in names}
    yield
    for name, original in originals.items():
        setattr(route, name, original)


def docs(*lines: str) -> list[Document]:
    return [Document(page_content=t, metadata={"source": "policy.pdf"}) for t in lines]


def test_chunk_id_is_deterministic():
    assert up.make_chunk_id("d1", "hello") == up.make_chunk_id("d1", "hello")
    assert up.make_chunk_id("d1", "hello").startswith("d1#")


def test_doc_id_ignores_presigned_query_string():
    a = up.doc_id_for_source("http://localhost:8333/b/policy.pdf?X-Amz-Signature=aaa")
    b = up.doc_id_for_source("http://localhost:8333/b/policy.pdf?X-Amz-Signature=bbb")
    assert a == b


def test_reingest_same_file_keeps_chunk_count(store):
    up.upsert_document(docs("leave is 12 days", "claims need receipts"), "hr", "d1")
    n = up.upsert_document(docs("leave is 12 days", "claims need receipts"), "hr", "d1")
    assert n == 2 and len(store) == 2
    assert {v["meta"]["version"] for v in store.values()} == {2}


def test_edited_line_removes_old_text(store):
    up.upsert_document(docs("leave is 12 days", "claims need receipts"), "hr", "d1")
    up.upsert_document(docs("leave is 15 days", "claims need receipts"), "hr", "d1", "2026-01-01")
    texts = {v["text"] for v in store.values()}
    assert texts == {"leave is 15 days", "claims need receipts"}
    assert all(v["meta"]["effective_date"] == "2026-01-01" for v in store.values())
    assert all("ingested_at" in v["meta"] for v in store.values())


def test_other_documents_untouched(store):
    up.upsert_document(docs("a"), "hr", "d1")
    up.upsert_document(docs("b"), "hr", "d2")
    up.upsert_document(docs("a2"), "hr", "d1")
    assert {v["text"] for v in store.values()} == {"a2", "b"}


def test_legacy_string_bm25_chunks_do_not_break_reingest():
    """BM25 indexes saved by old versions hold plain strings, not dicts (regression: 'str' has no attribute 'get')."""
    import asyncio
    from app.api import route

    saved = {}

    async def fake_load(_):
        return {"chunks": ["old plain string chunk", {"text": "dict chunk", "source": "a", "doc_id": "d9"}]}

    async def fake_save(ns, data):
        saved.update(data)

    route.load_bm25_index, route.save_bm25_index = fake_load, fake_save
    route.load_document = lambda source, source_type: docs("leave is 15 days")
    route.upsert_document = lambda chunks, ns, doc_id, eff, **_: 1
    req = route.IngestionRequest(namespace="hr", source=[{"path": "p.pdf", "type": "pdf"}])
    asyncio.run(route.ingest(req))
    texts = [c["text"] for c in saved["chunks"]]
    assert texts == ["old plain string chunk", "dict chunk", "leave is 15 days"]


def _ingest(sources, loader, monkeypatch_calls):
    import asyncio
    from app.api import route

    async def fake_load(_):
        return None

    async def fake_save(ns, data):
        monkeypatch_calls["saved"] = data

    route.load_bm25_index, route.save_bm25_index = fake_load, fake_save
    route.load_document = loader
    route.upsert_document = lambda chunks, ns, doc_id, eff, **_: monkeypatch_calls.setdefault("upserts", []).append(doc_id) or len(chunks)
    return asyncio.run(route.ingest(route.IngestionRequest(namespace="hr", source=sources)))


def test_blank_file_is_rejected_and_does_not_touch_index():
    import pytest
    from fastapi import HTTPException
    calls: dict = {}
    with pytest.raises(HTTPException) as err:
        _ingest([{"path": "blank.pdf", "type": "pdf"}], lambda source, source_type: [Document(page_content="  \n", metadata={})], calls)
    assert err.value.status_code == 422 and "No text could be extracted from blank.pdf" in err.value.detail
    assert "upserts" not in calls and "saved" not in calls  # old version of the document is untouched


def test_blank_among_good_files_gives_partial_with_warning():
    calls: dict = {}
    loader = lambda source, source_type: docs("leave is 15 days") if source == "good.md" else [Document(page_content="", metadata={})]
    res = _ingest([{"path": "good.md", "type": "markdown"}, {"path": "blank.md", "type": "markdown"}], loader, calls)
    assert res.status == "partial" and res.chunks_created == 1
    assert any("blank.md: no extractable text" in w for w in res.warnings)


def test_display_name_strips_url_query_encoding_and_upload_uuid():
    from app.api.route import display_name
    url = "http://seaweedfs:8333/ingestion-uploads/d43983db-bd57-45a0-ba52-95d5972a6fe6-New%20Microsoft%20Word%20Document.pdf?X-Amz-Signature=abc"
    assert display_name(url) == "New Microsoft Word Document.pdf"


def test_near_blank_markdown_is_rejected_not_silently_accepted():
    import pytest
    from fastapi import HTTPException
    for text in ("# Title", "TODO"):
        with pytest.raises(HTTPException) as err:
            _ingest([{"path": "n.md", "type": "markdown"}], lambda source, source_type, t=text: [Document(page_content=t, metadata={})], {})
        assert err.value.status_code == 422
