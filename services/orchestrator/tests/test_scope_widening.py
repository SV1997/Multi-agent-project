"""Orchestrator-driven scope widening in the corrective retrieval loop.

Run from services/orchestrator:  python -m pytest tests/test_scope_widening.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))
from app.graph.agents.base import agent_factory as af  # noqa: E402
from app.graph.frames.node import debug_payload  # noqa: E402
from test_retrieval_payload import FakeClient, FakeResponse, retrieve  # noqa: E402,F401

FRAME = {"localize_categories": ["earned_leave"], "localize_wider_categories": ["leave", "earned_leave"]}


def insufficient(**over):
    return {"retrieval_quality": "insufficient", "retrieval_source": "vector", "retrieval_attempts": 1,
            "max_retrieval_attempts": 3, **FRAME, **over}


def route(state, methods=("vector", "sql")):
    return af.grading_route(state, list(methods))


# ---------------------------------------------------------------- the payload per level

def test_level_zero_sends_the_frame_and_the_wider_categories(monkeypatch):
    payload, _ = retrieve(monkeypatch, **FRAME, localize_scope_level=0)
    assert payload["categories"] == ["earned_leave"] and payload["wider_categories"] == ["leave", "earned_leave"]


def test_level_one_sends_the_parents_family_only(monkeypatch):
    payload, _ = retrieve(monkeypatch, **FRAME, localize_scope_level=1)
    assert payload["categories"] == ["leave", "earned_leave"] and "wider_categories" not in payload


def test_level_two_sends_no_categories(monkeypatch):
    payload, _ = retrieve(monkeypatch, **FRAME, localize_scope_level=2)
    assert "categories" not in payload and "wider_categories" not in payload


# ---------------------------------------------------------------- the level the answer prompt sees

def test_fallback_level_is_the_larger_of_service_and_scope_level(monkeypatch):
    monkeypatch.setattr(FakeResponse, "json", lambda self: {"results": [], "fallback_level": 1, "fallback_used": True})
    _, result = retrieve(monkeypatch, **FRAME, localize_scope_level=0)
    assert result["localize_fallback_level"] == 1
    monkeypatch.setattr(FakeResponse, "json", lambda self: {"results": [], "fallback_level": 0})
    _, result = retrieve(monkeypatch, **FRAME, localize_scope_level=1)
    assert result["localize_fallback_level"] == 1 and result["localize_fallback_used"] is True


def test_level_two_is_reported_even_though_the_service_says_not_localized(monkeypatch):
    monkeypatch.setattr(FakeResponse, "json", lambda self: {"results": [], "localized": False, "fallback_level": 0})
    _, result = retrieve(monkeypatch, **FRAME, localize_scope_level=2)
    assert result["localize_fallback_level"] == 2


def test_a_failed_retrieval_at_a_wider_level_still_reports_no_level(monkeypatch):
    monkeypatch.setattr(FakeResponse, "json", lambda self: {"results": [], "failed": True})
    _, result = retrieve(monkeypatch, **FRAME, localize_scope_level=2)
    assert result["localize_fallback_level"] is None


# ---------------------------------------------------------------- routing

def test_widens_when_evidence_is_insufficient(monkeypatch):
    assert route(insufficient()) == "widen_scope"


def test_never_widens_without_categories_or_for_sql(monkeypatch):
    assert route(insufficient(localize_categories=None)) == "rewrite_query"
    assert route(insufficient(retrieval_source="sql"), ("vector", "sql")) == "fallback_to_vector"


def test_never_widens_at_level_two_from_either_source(monkeypatch):
    assert route(insufficient(localize_scope_level=2)) == "rewrite_query"
    assert route(insufficient(localize_fallback_level=2)) == "rewrite_query"


def test_relevant_or_tool_answerable_evidence_never_widens(monkeypatch):
    assert route(insufficient(retrieval_quality="relevant")) == "reason"
    assert route(insufficient(retrieval_can_use_tool=True)) == "reason"


def test_widening_comes_before_sql_fallback_and_giving_up(monkeypatch):
    assert route(insufficient(retrieval_attempts=3)) == "widen_scope"
    assert route(insufficient(retrieval_attempts=3, localize_scope_level=2), ("vector", "sql")) == "fallback_to_sql"
    assert route(insufficient(retrieval_attempts=3, localize_scope_level=2), ("vector",)) == "insufficient_evidence"


# ---------------------------------------------------------------- the widen_scope step and the loop guard

def test_widening_steps_one_level_and_adds_an_attempt():
    assert af.widen_scope_update(insufficient(localize_scope_level=0)) == {"localize_scope_level": 1, "max_retrieval_attempts": 4}
    assert af.widen_scope_update(insufficient(localize_scope_level=1))["localize_scope_level"] == 2


def test_without_wider_categories_level_one_is_skipped():
    assert af.widen_scope_update(insufficient(localize_wider_categories=None, localize_scope_level=0))["localize_scope_level"] == 2


def test_a_third_widening_is_never_chosen(monkeypatch):
    state = insufficient(localize_scope_level=0)
    widenings = 0
    while route(state) == "widen_scope":
        state = {**state, **af.widen_scope_update(state)}
        widenings += 1
        assert widenings <= 2
    assert widenings == 2


def test_widening_does_not_use_up_the_rewrite_attempts(monkeypatch):
    state = insufficient(localize_scope_level=0, retrieval_attempts=1)
    for _ in range(2):
        state = {**state, **af.widen_scope_update(state), "retrieval_attempts": state["retrieval_attempts"] + 1}
    assert state["localize_scope_level"] == 2 and state["retrieval_attempts"] == 3
    assert route(state) == "rewrite_query"


# ---------------------------------------------------------------- evaluation visibility

def test_the_debug_payload_shows_the_scope_level():
    values = {"localize_frame_ids": ["f"], "localize_scope_level": 2}
    assert debug_payload(values)["scope_level"] == 2
