"""Phase 3: the orchestrator asks retrieval for specific categories only when it has some.

Run from services/orchestrator:  python -m pytest tests/test_retrieval_payload.py
httpx is replaced by a fake that records the request, so no service is called.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))
from app.graph.agents.base import nodes  # noqa: E402


class FakeResponse:
    def raise_for_status(self):
        pass

    def json(self):
        return {"results": [{"source": "s", "content": "c"}]}


class FakeClient:
    sent: dict = {}

    def __init__(self, **_):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def post(self, url, json, headers):
        FakeClient.sent = {"url": url, "json": json}
        return FakeResponse()


def retrieve(monkeypatch, **state):
    monkeypatch.setattr(nodes.httpx, "AsyncClient", FakeClient)
    base = {"domain": "hr", "search_query": "how many leave days", "messages": []}
    result = asyncio.run(nodes.retrieve_context({**base, **state}))
    return FakeClient.sent["json"], result


def test_without_categories_the_request_is_exactly_what_it_was(monkeypatch):
    payload, _ = retrieve(monkeypatch)
    assert payload == {"query": "how many leave days", "namespace": "hr", "top_k": 5}


def test_empty_categories_are_not_sent(monkeypatch):
    assert "categories" not in retrieve(monkeypatch, localize_categories=[])[0]
    assert "categories" not in retrieve(monkeypatch, localize_categories=None)[0]


def test_categories_from_the_frame_are_sent(monkeypatch):
    payload, _ = retrieve(monkeypatch, localize_categories=["earned_leave", "leave"])
    assert payload == {"query": "how many leave days", "namespace": "hr", "top_k": 5,
                       "categories": ["earned_leave", "leave"]}


def test_the_returned_chunks_and_attempt_counter_are_unchanged(monkeypatch):
    _, result = retrieve(monkeypatch, localize_categories=["leave"], retrieval_attempts=2)
    assert result == {"retrieved_context": [{"source": "s", "content": "c"}], "retrieval_attempts": 3}
