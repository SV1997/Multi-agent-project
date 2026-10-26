"""Feature 5: re-ranking behind RERANK_ENABLED. Run from services/retrieval-service: python -m pytest tests/test_rerank.py"""
import asyncio
import os
import sys
import types

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))
fake_emb = types.ModuleType("shared.embeddings.embeddings")
fake_emb.embeddings = object()
sys.modules.setdefault("shared.embeddings.embeddings", fake_emb)

from langchain_core.documents import Document  # noqa: E402
from app.core import config  # noqa: E402
from app.pinecone import namespace_router as ns  # noqa: E402
from app.pinecone import reranker  # noqa: E402
from shared.contracts.schema import RetrievalQuery, RetrievedChunk  # noqa: E402

CORPUS = [Document(page_content=f"chunk {i}", metadata={"source": "s"}) for i in range(20)]


class FakeStore:
    def __init__(self, **_): pass

    def similarity_search_with_score(self, query, k):
        return [(d, 0.0) for d in CORPUS[:k]]  # vector rank == corpus order


async def _no_bm25(_):
    return None


def _setup(monkeypatch, enabled: bool):
    monkeypatch.setattr(ns, "PineconeVectorStore", FakeStore)
    monkeypatch.setattr(ns, "load_bm25", _no_bm25)
    monkeypatch.setattr(config, "RERANK_ENABLED", enabled)
    # cross-encoder stand-in: prefers the LAST chunk, the opposite of the fused order
    monkeypatch.setattr(reranker, "_load_scorer", lambda: (lambda pairs: [int(t.split()[1]) for _, t in pairs]))


def _query():
    return asyncio.run(ns.query_namespace(RetrievalQuery(query="q", namespace="hr", top_k=5)))


def test_flag_off_keeps_existing_behaviour(monkeypatch):
    _setup(monkeypatch, False)
    assert [c.content for c in _query().results] == [f"chunk {i}" for i in range(5)]


def test_flag_on_reranks_top20_to_top5(monkeypatch):
    _setup(monkeypatch, True)
    assert [c.content for c in _query().results] == [f"chunk {i}" for i in (19, 18, 17, 16, 15)]


def test_scorer_failure_falls_back_to_fused_order():
    chunks = [RetrievedChunk(content=f"c{i}", score=1.0, source="s") for i in range(8)]

    def boom(_):
        raise RuntimeError("model missing")

    assert [c.content for c in reranker.rerank("q", chunks, 5, scorer=boom)] == [f"c{i}" for i in range(5)]


def test_recall_at_k_metric():
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../scripts"))
    from compare_rerank import recall_at_k
    assert recall_at_k(["Leave is 15 days", "x"], ["15 days", "missing"]) == 0.5
