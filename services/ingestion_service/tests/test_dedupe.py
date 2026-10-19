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
