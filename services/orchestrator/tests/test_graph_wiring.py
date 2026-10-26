"""Phase 4: the real supervisor graph is wired the way the frame step needs.
Run from services/orchestrator:  python -m pytest tests/test_graph_wiring.py

The real graph is built with dummy API keys. Building it connects to nothing; no model is called.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))


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


DOMAIN_AGENTS = ("legal_agent", "hr_agent", "finance_agent", "support_agent", "engineering_agent")


@pytest.mark.parametrize("level", ["off", "filter", "full"])
def test_the_frame_step_sits_between_authorization_and_the_domain_agents(supervisor, monkeypatch, level):
    edges = edges_of(build(supervisor, monkeypatch, level))

    assert ("check_authorization", "frame_query") in edges
    assert ("check_authorization", "access_denied") in edges                       # denied users still stop here
    for agent in DOMAIN_AGENTS:
        assert ("check_authorization", agent) not in edges                         # no way around the frame step
        assert ("frame_query", agent) in edges
    assert ("frame_query", "ask_for_slot") in edges and ("ask_for_slot", "__end__") in edges


@pytest.mark.parametrize("level", ["off", "full"])
def test_the_trace_step_runs_after_the_review_gate_and_before_memory(supervisor, monkeypatch, level):
    edges = edges_of(build(supervisor, monkeypatch, level))
    assert ("human_review_gate", "trace_query") in edges and ("trace_query", "memory_add") in edges
    assert ("human_review_gate", "memory_add") not in edges


def test_the_rest_of_the_graph_is_unchanged(supervisor, monkeypatch):
    edges = edges_of(build(supervisor, monkeypatch, "off"))
    for edge in [("classify_domain", "check_authorization"), ("classify_domain", "classification_failed"),
                 ("memory_add", "extract_memories"), ("extract_memories", "__end__"),
                 ("access_denied", "__end__"), ("hr_agent", "human_review_gate")]:
        assert edge in edges


def test_the_graph_has_the_same_shape_at_every_level(supervisor, monkeypatch):
    shapes = {level: edges_of(build(supervisor, monkeypatch, level)) for level in ("off", "filter", "prompt", "full")}
    assert shapes["off"] == shapes["filter"] == shapes["prompt"] == shapes["full"]


def test_with_localize_off_no_frames_or_taxonomy_are_loaded(supervisor, monkeypatch):
    def must_not_run(*_args, **_kwargs):
        raise AssertionError("loaded while LOCALIZE=off")
    monkeypatch.setattr(supervisor, "load_taxonomy", must_not_run)
    monkeypatch.setattr(supervisor, "load_registry", must_not_run)
    build(supervisor, monkeypatch, "off")                                          # does not raise


def test_with_localize_on_the_real_frames_are_validated_at_startup(supervisor, monkeypatch):
    calls = []
    real = supervisor.load_registry
    monkeypatch.setattr(supervisor, "load_registry", lambda taxonomy: calls.append(1) or real(taxonomy))
    build(supervisor, monkeypatch, "filter")
    assert calls == [1]


def test_an_invalid_frames_file_stops_startup_when_localize_is_on(supervisor, monkeypatch):
    from app.graph.frames.registry import FrameError

    def broken(_taxonomy):
        raise FrameError("frames are invalid: hr: frame 'hr.x': unknown category 'nope'")
    monkeypatch.setattr(supervisor, "load_registry", broken)

    with pytest.raises(FrameError, match="unknown category 'nope'"):
        build(supervisor, monkeypatch, "full")
    build(supervisor, monkeypatch, "off")                                          # but off never looks at the frames


@pytest.mark.parametrize("level, expects_taxonomy", [("off", False), ("filter", True), ("full", True)])
def test_the_frame_step_gets_the_taxonomy_for_widening_only_when_localization_is_on(supervisor, monkeypatch, level, expects_taxonomy):
    seen = {}
    real = supervisor.make_frame_query_node
    monkeypatch.setattr(supervisor, "make_frame_query_node",
                        lambda *args, **kwargs: seen.update(kwargs) or real(*args, **kwargs))
    build(supervisor, monkeypatch, level)
    assert (seen["taxonomy"] is not None) is expects_taxonomy
