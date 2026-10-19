"""Feature 2 (offline): conflict_detected forces human review and is part of the schema.
Run from services/orchestrator:  python -m pytest tests/test_conflict.py
The live scenario (12 vs 15 leave days) is scripts/conflict_e2e.py.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))

from app.graph.agents.base.agent_factory import apply_conflict_policy  # noqa: E402
from shared.contracts.schema import AgentAnswer, AgentAnswerLLM  # noqa: E402


def test_conflict_forces_review():
    assert apply_conflict_policy(False, True) is True


def test_no_conflict_keeps_llm_decision():
    assert apply_conflict_policy(False, False) is False
    assert apply_conflict_policy(True, False) is True


def test_schema_defaults_to_no_conflict():
    assert AgentAnswerLLM(confidence=0.9).conflict_detected is False
    a = AgentAnswer(domain="hr", answer="x", sources=[], confidence=1.0, context=[])
    assert a.conflict_detected is False
