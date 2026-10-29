"""The real supervisor graph has the frame step between authorization and the domain agents.

Run from services/orchestrator:  python -m pytest tests/test_graph_wiring.py
The real graph is built with dummy API keys. Building it connects to nothing; no model is called.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))

DOMAIN_AGENTS = ("legal_agent", "hr_agent", "finance_agent", "support_agent", "engineering_agent")


@pytest.fixture(scope="module")
def supervisor():
    os.environ.setdefault("GROQ_API_KEY", "dummy-key-for-tests")
    os.environ.setdefault("OPENAI_API_KEY", "dummy-key-for-tests")
    from app.graph import supervisor as module
    return module


def build(supervisor, monkeypatch, level):
    from app.core import config
    monkeypatch.setattr(config, "LOCALIZE", level)
    return supervisor.set_supervisor_agent(None, None)


def edges_of(graph):
    return {(e.source, e.target) for e in graph.get_graph().edges}


def test_the_frame_step_sits_between_authorization_and_the_domain_agents(supervisor, monkeypatch):
    edges = edges_of(build(supervisor, monkeypatch, "off"))
    assert ("check_authorization", "frame_query") in edges
    for agent in DOMAIN_AGENTS:
        assert ("check_authorization", agent) not in edges                         # no way around the frame step
        assert ("frame_query", agent) in edges
    assert ("frame_query", "access_denied") in edges                              # denied users still stop here


def test_there_is_no_clarifying_question_and_no_trace_step(supervisor, monkeypatch):
    edges = edges_of(build(supervisor, monkeypatch, "off"))
    names = {name for edge in edges for name in edge}
    assert not names & {"ask_for_slot", "trace_query"}
    assert ("human_review_gate", "memory_add") in edges


def test_the_rest_of_the_graph_is_unchanged(supervisor, monkeypatch):
    edges = edges_of(build(supervisor, monkeypatch, "off"))
    for edge in [("classify_domain", "check_authorization"), ("classify_domain", "classification_failed"),
                 ("memory_add", "extract_memories"), ("extract_memories", "__end__"),
                 ("access_denied", "__end__"), ("hr_agent", "human_review_gate")]:
        assert edge in edges


def test_the_graph_has_the_same_shape_whether_localization_is_off_or_on(supervisor, monkeypatch):
    assert edges_of(build(supervisor, monkeypatch, "off")) == edges_of(build(supervisor, monkeypatch, "on"))


def test_with_localize_off_the_frames_are_not_even_loaded(supervisor, monkeypatch):
    def must_not_run(*_args, **_kwargs):
        raise AssertionError("loaded while LOCALIZE=off")
    monkeypatch.setattr(supervisor, "load_registry", must_not_run)
    build(supervisor, monkeypatch, "off")                                          # does not raise


def test_with_localize_on_a_broken_frames_file_stops_startup(supervisor, monkeypatch):
    def broken(_taxonomy):
        raise ValueError("frames.yaml is invalid: hr: frame 'hr.x': unknown category 'nope'")
    monkeypatch.setattr(supervisor, "load_registry", broken)

    with pytest.raises(ValueError, match="unknown category 'nope'"):
        build(supervisor, monkeypatch, "on")
    build(supervisor, monkeypatch, "off")                                          # but off never looks at the frames
