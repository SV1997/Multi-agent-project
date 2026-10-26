"""Phase 2: new chunks are tagged with the taxonomy's labels at ingestion.

Run from services/ingestion_service:  python -m pytest tests/test_tagging.py
Pinecone, the database and the document loader are faked; the real upsert_document and the real /ingest route run.
"""
import os
import sys
import types
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from langchain_core.documents import Document

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../scripts"))      # for the backfill cross-check
fake_emb = types.ModuleType("shared.embeddings.embeddings")
fake_emb.embeddings = object()
sys.modules.setdefault("shared.embeddings.embeddings", fake_emb)

from shared.taxonomy.taxonomy import parse_taxonomy  # noqa: E402
from shared.contracts.schema import SourceItem  # noqa: E402
from app.pinecone import upsert as up  # noqa: E402
from app.api import route  # noqa: E402
from app.core import security  # noqa: E402
from app.main import app  # noqa: E402

TAX = parse_taxonomy({
    "hr": {
        "categories": {
            "leave": {"description": "All leave rules", "parents": []},
            "earned_leave": {"description": "Earned leave", "parents": ["leave"]},
        },
        "documents": {"handbook.pdf": {"title": "HR Handbook", "categories": ["leave", "earned_leave"]}},
    }
})

SIGNED = "http://seaweed:8333/bucket/0f8fad5b-d9cb-469f-a165-70867728950e-handbook.pdf?X-Amz-Signature=abc"


class FakeIndex:
    def __init__(self, store):
        self.store = store

    def list(self, prefix="", namespace=None):
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


def chunks(source=SIGNED, **extra):
    return [Document(page_content=text, metadata={"source": source, "title": "Old PDF title", **extra})
            for text in ("Earned leave is 24 days", "Claims need receipts")]


# ---------------------------------------------------------------- upsert_document

def test_chunks_are_tagged_using_the_uploaded_file_name(store):
    up.upsert_document(chunks(file_name="handbook.pdf"), "hr", "d1", taxonomy=TAX)

    for entry in store.values():
        meta = entry["meta"]
        assert meta["categories"] == ["leave", "earned_leave"] and meta["is_content"] is True
        assert meta["title"] == "HR Handbook" and meta["original_title"] == "Old PDF title"
        assert meta["file_name"] == "handbook.pdf"


def test_without_the_file_name_a_signed_source_cannot_be_matched(store):
    up.upsert_document(chunks(), "hr", "d1", taxonomy=TAX)
    assert {e["meta"]["categories"][0] for e in store.values()} == {"uncategorized"}


def test_a_plain_url_source_is_matched_by_its_last_segment(store):
    up.upsert_document(chunks(source="https://example.com/docs/handbook.pdf"), "hr", "d1", taxonomy=TAX)
    assert all(e["meta"]["categories"] == ["leave", "earned_leave"] for e in store.values())


def test_without_a_taxonomy_chunks_are_stored_exactly_as_before(store):
    up.upsert_document(chunks(file_name="handbook.pdf"), "hr", "d1")
    for entry in store.values():
        assert not {"categories", "is_content", "original_title"} & set(entry["meta"])
        assert entry["meta"]["title"] == "Old PDF title"


def test_reingesting_keeps_the_tags_identical(store):
    up.upsert_document(chunks(file_name="handbook.pdf"), "hr", "d1", taxonomy=TAX)
    first = {k: dict(v["meta"]) for k, v in store.items()}
    up.upsert_document(chunks(file_name="handbook.pdf"), "hr", "d1", taxonomy=TAX)

    assert set(store) == set(first)
    for chunk_id, entry in store.items():
        for key in ("categories", "is_content", "title", "file_name"):
            assert entry["meta"][key] == first[chunk_id][key]


# ---------------------------------------------------------------- the contract

def test_a_source_item_may_carry_the_uploaded_file_name():
    assert SourceItem(path="p", type="pdf", file_name="handbook.pdf").file_name == "handbook.pdf"
    assert SourceItem(path="p", type="pdf").file_name is None


# ---------------------------------------------------------------- the /ingest route

@pytest.fixture
def client(store, monkeypatch):
    saved = {}

    async def no_index(_):
        return None

    async def save(namespace, data):
        saved[namespace] = data

    monkeypatch.setattr(security, "INTERNAL_SHARED_SECRET", "test-secret")
    monkeypatch.setattr(route, "load_taxonomy", lambda: TAX)
    monkeypatch.setattr(route, "load_document", lambda source, source_type: chunks(source=source))
    monkeypatch.setattr(route, "split_documents", lambda docs: docs)
    monkeypatch.setattr(route, "assess_parse_quality", lambda *a: [])
    monkeypatch.setattr(route, "assess_chunking", lambda *a: [])
    monkeypatch.setattr(route, "load_bm25_index", no_index)
    monkeypatch.setattr(route, "save_bm25_index", save)
    test_client = TestClient(app)
    test_client.saved_bm25 = saved
    return test_client


def post_ingest(client, **source_extra):
    body = {"namespace": "hr", "source": [{"path": SIGNED, "type": "pdf", "doc_id": "d1", **source_extra}]}
    return client.post("/api/v1/ingest", json=body, headers={"x-internal-secret": "test-secret"})


def test_the_route_tags_pinecone_chunks_and_keyword_chunks_alike(client, store):
    response = post_ingest(client, file_name="handbook.pdf")

    assert response.status_code == 200 and response.json()["warnings"] == []
    assert all(e["meta"]["categories"] == ["leave", "earned_leave"] and e["meta"]["file_name"] == "handbook.pdf"
               for e in store.values())
    bm25_chunks = client.saved_bm25["hr"]["chunks"]
    assert len(bm25_chunks) == 2
    for chunk in bm25_chunks:
        assert chunk["categories"] == ["leave", "earned_leave"] and chunk["is_content"] is True
        assert chunk["file_name"] == "handbook.pdf" and chunk["doc_id"] == "d1"
        assert chunk["title"] == "HR Handbook"          # the taxonomy's title, not the loader's "Old PDF title"


def test_a_source_without_a_file_name_is_ingested_and_uncategorized(client, store):
    assert post_ingest(client).status_code == 200
    assert {e["meta"]["categories"][0] for e in store.values()} == {"uncategorized"}
    assert all("file_name" not in c for c in client.saved_bm25["hr"]["chunks"])


def test_a_broken_taxonomy_does_not_stop_ingestion_but_is_reported(client, store, monkeypatch):
    def broken():
        raise ValueError("policy taxonomy is invalid")
    monkeypatch.setattr(route, "load_taxonomy", broken)

    response = post_ingest(client, file_name="handbook.pdf")

    assert response.status_code == 200 and response.json()["status"] == "success"
    assert len(store) == 2 and all("categories" not in e["meta"] for e in store.values())
    assert any("taxonomy unavailable" in w and "backfill.py" in w for w in response.json()["warnings"])
    assert all("categories" not in c for c in client.saved_bm25["hr"]["chunks"])


def test_a_backfill_run_right_after_ingestion_has_nothing_left_to_change(client, store):
    """The two ways of tagging a chunk (at ingestion, and the backfill script) must agree exactly."""
    import backfill

    post_ingest(client, file_name="handbook.pdf")
    updates, targets, stats = backfill.plan_pinecone(FakeIndex(store), TAX, ["hr"])

    assert updates == [] and stats["hr"]["already_correct"] == 2
    _, bm25_stats = backfill.plan_bm25(client.saved_bm25["hr"]["chunks"], "hr", TAX, targets)
    assert bm25_stats.get("to_update", 0) == 0 and bm25_stats["already_correct"] == 2
