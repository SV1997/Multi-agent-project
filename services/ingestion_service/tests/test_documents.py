"""List / delete a whole document: Pinecone helpers and the two HTTP routes.

Run from services/ingestion_service:  python -m pytest tests/test_documents.py
Uses an in-memory fake Pinecone index; database calls in the routes are replaced.
"""
import os
import sys
import types
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from rank_bm25 import BM25Okapi

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))
fake_emb = types.ModuleType("shared.embeddings.embeddings")
fake_emb.embeddings = object()
sys.modules.setdefault("shared.embeddings.embeddings", fake_emb)

from app.pinecone import documents as docs  # noqa: E402
from app.api import route  # noqa: E402
from app.core import security  # noqa: E402
from app.main import app  # noqa: E402


class FakeIndex:
    """Serverless semantics: list by id prefix (all ids when no prefix), fetch by id, delete by id."""

    def __init__(self, store: dict):
        self.store = store          # chunk_id -> metadata
        self.deleted: list[str] = []
        self.fetch_calls: list[int] = []

    def list(self, namespace, prefix=""):
        yield [i for i in self.store if i.startswith(prefix)]

    def fetch(self, ids, namespace):
        self.fetch_calls.append(len(ids))
        return SimpleNamespace(vectors={i: SimpleNamespace(metadata=self.store[i]) for i in ids if i in self.store})

    def delete(self, ids, namespace):
        assert len(ids) <= 1000, "Pinecone rejects more than 1000 ids per delete"
        for i in ids:
            self.deleted.append(i)
            self.store.pop(i, None)


def chunk(doc_id, n, **meta):
    return f"{doc_id}#{n:012d}", {"source": f"http://seaweed/bucket/{doc_id}.pdf", "doc_id": doc_id, **meta}


def make_store(*doc_chunk_counts):
    store = {}
    for doc_id, count in doc_chunk_counts:
        for n in range(count):
            cid, meta = chunk(doc_id, n, version=2.0, ingested_at="2026-10-20T10:00:00+00:00")
            store[cid] = meta
    return store


# ---------- Pinecone helpers ----------

def test_list_documents_groups_chunks_by_document():
    index = FakeIndex(make_store(("aaaa", 3), ("bbbb", 1)))
    result = {d["doc_id"]: d for d in docs.list_documents("hr", index=index)}

    assert set(result) == {"aaaa", "bbbb"}
    assert result["aaaa"]["chunks"] == 3 and result["bbbb"]["chunks"] == 1
    assert result["aaaa"]["version"] == 2            # 2.0 from Pinecone becomes an int
    assert result["aaaa"]["source"].endswith("aaaa.pdf")
    assert result["aaaa"]["ingested_at"] == "2026-10-20T10:00:00+00:00"


def test_list_documents_fetches_one_chunk_per_document_in_batches_of_100():
    index = FakeIndex(make_store(*[(f"doc{i:04d}", 5) for i in range(230)]))   # 1150 chunks, 230 documents
    result = docs.list_documents("hr", index=index)

    assert len(result) == 230
    assert index.fetch_calls == [100, 100, 30]       # 230 sample chunks, not 1150


def test_list_documents_empty_namespace():
    assert docs.list_documents("hr", index=FakeIndex({})) == []


def test_delete_removes_only_the_target_documents_chunks():
    store = make_store(("ab", 2), ("abc", 2), ("zzzz", 1))   # "ab" is a string prefix of "abc"
    index = FakeIndex(store)

    assert docs.delete_document_chunks("hr", "ab", index=index) == 2
    assert sorted(index.store) == sorted(i for i in store if i.startswith(("abc#", "zzzz#")))
    assert docs.delete_document_chunks("hr", "ab", index=index) == 0     # already gone


def test_delete_splits_requests_at_1000_ids():
    index = FakeIndex(make_store(("big", 2300)))
    assert docs.delete_document_chunks("hr", "big", index=index) == 2300
    assert index.store == {}                        # FakeIndex.delete asserts each call is <= 1000


def test_chunks_without_document_keeps_other_documents_and_legacy_strings():
    chunks = [
        {"text": "a1", "doc_id": "aaaa"},
        {"text": "b1", "doc_id": "bbbb"},
        {"text": "a2", "doc_id": "aaaa"},
        "old plain string chunk",
    ]
    kept = docs.chunks_without_document(chunks, "aaaa")
    assert [c["text"] for c in kept] == ["b1", "old plain string chunk"]


# ---------- HTTP routes ----------

HEADERS = {"x-internal-secret": "test-secret"}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(security, "INTERNAL_SHARED_SECRET", "test-secret")
    return TestClient(app)


@pytest.fixture
def db(monkeypatch):
    """Replace the Postgres calls with an in-memory keyword index and record what the route did."""
    state = SimpleNamespace(
        bm25={"chunks": [], "Bm25": None}, saved=None, index_deleted=False, extractions=0, pinecone_deleted=0,
    )

    async def load(namespace):
        return state.bm25

    async def save(namespace, data):
        state.saved = data

    async def delete_index(namespace):
        state.index_deleted = True

    async def delete_extr(doc_id, namespace):
        return state.extractions

    monkeypatch.setattr(route, "load_bm25_index", load)
    monkeypatch.setattr(route, "save_bm25_index", save)
    monkeypatch.setattr(route, "delete_bm25_index", delete_index)
    monkeypatch.setattr(route, "delete_extractions", delete_extr)
    monkeypatch.setattr(route, "delete_document_chunks", lambda ns, doc_id: state.pinecone_deleted)
    return state


def test_routes_require_the_internal_secret(client):
    wrong = {"x-internal-secret": "wrong"}
    assert client.get("/api/v1/documents", params={"namespace": "hr"}, headers=wrong).status_code == 403
    assert client.delete("/api/v1/documents/abc123", params={"namespace": "hr"}, headers=wrong).status_code == 403
    # no header at all is rejected before the secret is compared (the header is declared as required)
    assert client.get("/api/v1/documents", params={"namespace": "hr"}).status_code == 422


def test_list_route_returns_readable_names_sorted(client, monkeypatch):
    monkeypatch.setattr(route, "list_documents", lambda ns: [
        {"doc_id": "b1", "chunks": 4, "source": "http://s/bucket/0f8fad5b-d9cb-469f-a165-70867728950e-Zebra%20policy.pdf?X-Amz=1",
         "version": 1, "ingested_at": None},
        {"doc_id": "a1", "chunks": 2, "source": "http://s/bucket/0f8fad5b-d9cb-469f-a165-70867728950e-alpha.pdf", "version": 3, "ingested_at": None},
        {"doc_id": "c1", "chunks": 1, "source": "", "version": None, "ingested_at": None},
    ])
    body = client.get("/api/v1/documents", params={"namespace": "hr"}, headers=HEADERS).json()

    assert body["namespace"] == "hr"
    assert [d["name"] for d in body["documents"]] == ["alpha.pdf", "c1", "Zebra policy.pdf"]   # upload prefix + query removed; id used when no source
    assert [d["file"] for d in body["documents"]] == ["alpha.pdf", "", "Zebra policy.pdf"]


def test_list_route_rejects_unknown_namespace(client):
    assert client.get("/api/v1/documents", params={"namespace": "nope"}, headers=HEADERS).status_code == 422


@pytest.mark.parametrize("bad_id", ["a%23b", "has%20space", "x" * 65])
def test_delete_route_rejects_malformed_document_ids(client, bad_id):
    r = client.delete(f"/api/v1/documents/{bad_id}", params={"namespace": "hr"}, headers=HEADERS)
    assert r.status_code == 422


def test_delete_route_removes_the_document_from_every_store(client, db):
    db.pinecone_deleted = 3
    db.extractions = 1
    db.bm25 = {"chunks": [{"text": "keep me", "doc_id": "other"}, {"text": "gone 1", "doc_id": "abc123"},
                          {"text": "gone 2", "doc_id": "abc123"}], "Bm25": None}

    r = client.delete("/api/v1/documents/abc123", params={"namespace": "legal"}, headers=HEADERS)

    assert r.status_code == 200
    assert r.json() == {"doc_id": "abc123", "namespace": "legal", "chunks_deleted": 3,
                        "keyword_chunks_removed": 2, "extractions_deleted": 1}
    assert [c["text"] for c in db.saved["chunks"]] == ["keep me"]
    assert isinstance(db.saved["Bm25"], BM25Okapi)       # rebuilt over the remaining chunks only
    assert not db.index_deleted


def test_delete_route_drops_the_keyword_index_when_the_last_document_goes(client, db):
    db.pinecone_deleted = 2
    db.bm25 = {"chunks": [{"text": "only", "doc_id": "abc123"}], "Bm25": None}

    r = client.delete("/api/v1/documents/abc123", params={"namespace": "hr"}, headers=HEADERS)

    assert r.status_code == 200
    assert db.index_deleted and db.saved is None         # BM25Okapi([]) would crash, so the row is removed


def test_delete_route_leaves_the_keyword_index_alone_when_the_document_is_not_in_it(client, db):
    db.pinecone_deleted = 2
    db.bm25 = {"chunks": [{"text": "x", "doc_id": "other"}], "Bm25": None}

    assert client.delete("/api/v1/documents/abc123", params={"namespace": "hr"}, headers=HEADERS).status_code == 200
    assert db.saved is None and not db.index_deleted


def test_delete_route_404_when_the_document_exists_nowhere(client, db):
    r = client.delete("/api/v1/documents/abc123", params={"namespace": "hr"}, headers=HEADERS)
    assert r.status_code == 404
    assert "abc123" in r.json()["detail"]


def test_delete_route_500_with_a_message_when_pinecone_fails(client, db, monkeypatch):
    def boom(ns, doc_id):
        raise RuntimeError("pinecone unavailable")
    monkeypatch.setattr(route, "delete_document_chunks", boom)

    r = client.delete("/api/v1/documents/abc123", params={"namespace": "hr"}, headers=HEADERS)
    assert r.status_code == 500 and "pinecone unavailable" in r.json()["detail"]
    assert db.saved is None                              # nothing else was touched after the failure


# ---------- older chunks: random ids, no doc_id, grouped by source (this is what the real index holds) ----------

def legacy_store(*source_chunk_counts, **extra):
    """{random uuid id: metadata} like the chunks ingested before deterministic ids existed."""
    store, n = {}, 0
    for source, count in source_chunk_counts:
        for _ in range(count):
            n += 1
            store[f"{n:08x}-b8e6-4630-bbe7-61e68be3cbc7"] = {"source": source, "text": f"chunk {n}", **extra}
    return store


def test_legacy_chunks_are_grouped_by_source_not_listed_one_by_one():
    index = FakeIndex(legacy_store(("/tmp/tmpAAAA.pdf", 74), ("/tmp/tmpBBBB.md", 8), ("https://gdpr-info.eu/", 27), title="T"))
    result = {d["source"]: d for d in docs.list_documents("legal", index=index)}

    assert len(result) == 3                                   # 109 chunks, 3 documents
    assert [result[s]["chunks"] for s in ("/tmp/tmpAAAA.pdf", "/tmp/tmpBBBB.md", "https://gdpr-info.eu/")] == [74, 8, 27]
    assert all(d["doc_id"].startswith(docs.LEGACY_PREFIX) for d in result.values())
    assert result["/tmp/tmpAAAA.pdf"]["title"] == "T" and result["/tmp/tmpAAAA.pdf"]["version"] is None


def test_current_and_legacy_documents_are_listed_together():
    store = make_store(("aaaa", 3))
    store.update(legacy_store(("/tmp/tmpOLD.pdf", 5)))
    result = {d["doc_id"]: d for d in docs.list_documents("hr", index=FakeIndex(store))}

    assert result["aaaa"]["chunks"] == 3 and result["aaaa"]["version"] == 2
    assert result[docs.legacy_key("/tmp/tmpOLD.pdf")]["chunks"] == 5
    assert len(result) == 2


def test_deleting_a_legacy_document_removes_only_chunks_from_that_source():
    store = make_store(("aaaa", 2))
    store.update(legacy_store(("/tmp/one.pdf", 3), ("/tmp/two.pdf", 4)))
    index = FakeIndex(store)

    assert docs.delete_document_chunks("hr", docs.legacy_key("/tmp/one.pdf"), index=index) == 3
    remaining = docs.list_documents("hr", index=index)
    assert sorted((d["doc_id"], d["chunks"]) for d in remaining) == sorted(
        [("aaaa", 2), (docs.legacy_key("/tmp/two.pdf"), 4)])


def test_deleting_a_current_document_leaves_legacy_chunks_alone():
    store = make_store(("aaaa", 2))
    store.update(legacy_store(("/tmp/one.pdf", 3)))
    index = FakeIndex(store)

    assert docs.delete_document_chunks("hr", "aaaa", index=index) == 2
    assert len(index.store) == 3 and all("#" not in i for i in index.store)


def test_a_legacy_chunk_without_a_source_is_its_own_document_and_can_be_deleted():
    index = FakeIndex({"deadbeef-0000-0000-0000-000000000000": {"text": "orphan"}})
    (only,) = docs.list_documents("hr", index=index)

    assert only["doc_id"] == "deadbeef-0000-0000-0000-000000000000" and only["chunks"] == 1
    assert docs.delete_document_chunks("hr", only["doc_id"], index=index) == 1
    assert index.store == {}


def test_legacy_keyword_chunks_are_matched_by_source():
    chunks = [
        {"text": "a1", "source": "/tmp/one.pdf"},                        # legacy: no doc_id
        {"text": "a2", "source": "/tmp/one.pdf"},
        {"text": "b1", "source": "/tmp/two.pdf"},
        {"text": "c1", "source": "x", "doc_id": "aaaa"},               # current
        "plain old string",
    ]
    kept = docs.chunks_without_document(chunks, docs.legacy_key("/tmp/one.pdf"))
    assert [c["text"] for c in kept] == ["b1", "c1", "plain old string"]


# ---------- readable names ----------

@pytest.mark.parametrize("source, title, expected", [
    ("/tmp/tmp5jdxnb7a.pdf", "Employee Handbook 2025", "Employee Handbook 2025"),    # temp name -> use the PDF title
    ("/tmp/tmp5jdxnb7a.pdf", "", "tmp5jdxnb7a.pdf"),                                  # nothing better available
    ("https://gdpr-info.eu/", "", "gdpr-info.eu"),                                    # bare site -> the address
    ("https://docs.docker.com/build/building/best-practices/", "", "docs.docker.com/build/building/best-practices"),
    ("https://gdpr-info.eu/", "General Data Protection Regulation", "General Data Protection Regulation"),
    ("http://s/bucket/0f8fad5b-d9cb-469f-a165-70867728950e-Leave%20policy.pdf?X-Amz-Signature=abc", "Some title", "Leave policy.pdf"),
    ("", "", "abc123"),                                                               # no source -> the id
])
def test_document_name(source, title, expected):
    assert route.document_name(source, title, "abc123") == expected
