"""The query rewriter is told why it is rewriting: what came back, what was missing, what was already tried.

Run from services/orchestrator:  python -m pytest tests/test_rewrite_prompt.py
No model is called; only the messages that would be sent are checked.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))
from app.graph.agents.base.rewrite_prompt import MAX_PASSAGES, PASSAGE_CHARS, passage_digest, rewrite_messages  # noqa: E402

STATE = {
    "original_query": "How many days off do I get?",
    "search_query": "days off",
    "tried_queries": ["How many days off do I get?", "days off"],
    "retrieved_context": [{"source": "hr/leave-process.pdf", "content": "To apply for leave,   submit the form\nto your manager."}],
    "retrieval_assessment": "The passages explain how to apply, not how many days are allowed.",
    "retrieval_missing": "the number of leave days per year",
}


def human_text(state=STATE, conversation="User: hi"):
    return rewrite_messages(state, conversation)[1].content


def test_the_prompt_carries_what_came_back_what_was_missing_and_what_was_tried():
    text = human_text()
    assert "hr/leave-process.pdf" in text and "To apply for leave, submit the form to your manager." in text
    assert "the number of leave days per year" in text
    assert "The passages explain how to apply" in text
    assert "- How many days off do I get?" in text and "- days off" in text
    assert "User: hi" in text


def test_the_system_message_says_why_it_is_rewriting_and_forbids_repeating():
    system = rewrite_messages(STATE, "none")[0].content
    assert "without enough evidence" in system
    assert "Do not repeat" in system and "Do not answer" in system


def test_passages_are_shortened_and_capped():
    chunks = [{"source": f"s{i}", "content": "x" * 1000} for i in range(10)]
    lines = passage_digest(chunks).splitlines()
    assert len(lines) == MAX_PASSAGES
    assert all(len(line) <= PASSAGE_CHARS + 20 for line in lines)


def test_no_passages_is_said_plainly():
    assert "returned no passages" in passage_digest([])
    assert "returned no passages" in passage_digest(None)


def test_missing_fields_do_not_break_the_prompt():
    text = human_text({"original_query": "q", "search_query": "q"})
    assert "- q" in text and "not given" in text
