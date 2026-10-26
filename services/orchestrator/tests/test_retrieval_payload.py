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


# ---------------------------------------------------------------- following the search plan (widening)

PLAN = [{"level": 0, "categories": ["earned_leave"]},
        {"level": 1, "categories": ["leave", "earned_leave", "sick_leave"]},
        {"level": 2, "categories": None}]


def test_each_search_in_a_question_follows_the_plan_one_level_wider(monkeypatch):
    sent, state = [], {"localize_levels": PLAN}
    for _ in range(3):
        payload, result = retrieve(monkeypatch, **state)
        sent.append(payload.get("categories"))
        state = {"localize_levels": PLAN, **{k: result[k] for k in ("retrieval_calls", "fallback_level", "levels_tried")}}

    assert sent == [["earned_leave"], ["leave", "earned_leave", "sick_leave"], None]        # the last level has no restriction
    assert state["fallback_level"] == 2 and state["levels_tried"] == [0, 1, 2] and state["retrieval_calls"] == 3


def test_the_first_search_records_level_zero_and_counts_itself(monkeypatch):
    _, result = retrieve(monkeypatch, localize_levels=PLAN)
    assert (result["retrieval_calls"], result["fallback_level"], result["levels_tried"]) == (1, 0, [0])


def test_a_search_beyond_the_last_level_stays_on_the_last_level(monkeypatch):
    payload, result = retrieve(monkeypatch, localize_levels=PLAN, retrieval_calls=7, levels_tried=[0, 1, 2])
    assert "categories" not in payload and result["fallback_level"] == 2 and result["retrieval_calls"] == 8


def test_a_skipped_level_keeps_its_number_in_the_trace(monkeypatch):
    plan = [{"level": 0, "categories": ["privacy"]}, {"level": 2, "categories": None}]
    _, second = retrieve(monkeypatch, localize_levels=plan, retrieval_calls=1, levels_tried=[0])
    assert second["fallback_level"] == 2 and second["levels_tried"] == [0, 2]


def test_a_plan_takes_precedence_over_the_flat_category_list(monkeypatch):
    payload, _ = retrieve(monkeypatch, localize_levels=PLAN, localize_categories=["something_else"])
    assert payload["categories"] == ["earned_leave"]


def test_without_a_plan_nothing_is_recorded_and_the_request_is_unchanged(monkeypatch):
    payload, result = retrieve(monkeypatch)
    assert payload == {"query": "how many leave days", "namespace": "hr", "top_k": 5}
    assert set(result) == {"retrieved_context", "retrieval_attempts"}
