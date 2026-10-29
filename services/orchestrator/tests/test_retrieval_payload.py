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
    _, result = retrieve(monkeypatch, retrieval_attempts=2)
    assert result == {"retrieved_context": [{"source": "s", "content": "c"}], "retrieval_attempts": 3}


# ---------------------------------------------------------------- remembering that the retrieval service fell back

def test_a_filtered_search_records_that_no_fallback_was_needed(monkeypatch):
    _, result = retrieve(monkeypatch, localize_categories=["leave"])
    assert result["localize_fallback_used"] is False


def test_a_fallback_reported_by_the_retrieval_service_is_kept_in_the_state(monkeypatch):
    monkeypatch.setattr(FakeResponse, "json", lambda self: {"results": [], "fallback_used": True})
    _, result = retrieve(monkeypatch, localize_categories=["leave"])
    assert result["localize_fallback_used"] is True


def test_an_unfiltered_search_leaves_the_fallback_flag_alone(monkeypatch):
    _, result = retrieve(monkeypatch)
    assert "localize_fallback_used" not in result


# ---------------------------------------------------------------- the wider level and which level answered

def test_the_wider_categories_are_sent_with_the_categories(monkeypatch):
    payload, _ = retrieve(monkeypatch, localize_categories=["earned_leave"], localize_wider_categories=["leave", "earned_leave"])
    assert payload["categories"] == ["earned_leave"] and payload["wider_categories"] == ["leave", "earned_leave"]


def test_wider_categories_alone_are_never_sent(monkeypatch):
    payload, _ = retrieve(monkeypatch, localize_wider_categories=["leave"])
    assert "wider_categories" not in payload and "categories" not in payload


def test_no_wider_level_means_nothing_extra_is_sent(monkeypatch):
    payload, _ = retrieve(monkeypatch, localize_categories=["leave"], localize_wider_categories=None)
    assert "wider_categories" not in payload


def test_the_level_the_retrieval_service_answered_at_is_kept_in_the_state(monkeypatch):
    monkeypatch.setattr(FakeResponse, "json", lambda self: {"results": [], "fallback_used": True, "fallback_level": 1})
    _, result = retrieve(monkeypatch, localize_categories=["earned_leave"], localize_wider_categories=["leave"])
    assert result["localize_fallback_used"] is True and result["localize_fallback_level"] == 1


def test_a_search_that_needed_no_widening_records_level_zero(monkeypatch):
    _, result = retrieve(monkeypatch, localize_categories=["leave"])
    assert result["localize_fallback_used"] is False and result["localize_fallback_level"] == 0
