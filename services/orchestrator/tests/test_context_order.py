"""Feature 6: best chunks at the edges of the prompt. Run from services/orchestrator: python -m pytest tests/test_context_order.py"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))
from app.core import config  # noqa: E402
from app.graph.agents.base.nodes import build_context_prompt, edge_order  # noqa: E402


def _state(n: int) -> dict:
    return {"retrieved_context": [{"source": f"s{i}", "content": f"c{i}"} for i in range(1, n + 1)]}


def _ranks(prompt: str) -> list[int]:
    return [int(p.split("]")[0].split(":")[0].replace("[Source", "")) for p in prompt.split("\n\n") if p.startswith("[Source")]


def test_edge_order():
    assert edge_order([1, 2, 3, 4, 5]) == [1, 3, 5, 4, 2]
    assert edge_order([1, 2]) == [1, 2] and edge_order([]) == []


def test_prompt_reordered_when_flag_on(monkeypatch):
    monkeypatch.setattr(config, "CONTEXT_REORDER", True)
    assert _ranks(build_context_prompt(_state(5))) == [1, 3, 5, 4, 2]


def test_prompt_unchanged_when_flag_off(monkeypatch):
    monkeypatch.setattr(config, "CONTEXT_REORDER", False)
    assert _ranks(build_context_prompt(_state(5))) == [1, 2, 3, 4, 5]
