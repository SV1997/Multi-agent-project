"""Tests for scripts/smoke_localize.py with fake gateway answers: no network, no services.

Run from the repo root:  uv run python -m pytest scripts/tests -q
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import smoke_localize as smoke  # noqa: E402
from shared.taxonomy.taxonomy import parse_taxonomy  # noqa: E402

TAX = parse_taxonomy({"hr": {
    "categories": {"leave": {"description": "All leave", "parents": []}, "earned_leave": {"description": "Earned", "parents": ["leave"]},
                   "payroll": {"description": "Pay", "parents": []}},
    "documents": {"earned.pdf": ["earned_leave"], "mix.pdf": ["leave", "payroll"]},
    "mixed": ["mix.pdf"],
}})

DAG = {"nodes": [{"type": "query"},
                 {"type": "evidence", "label": "https://x/earned.pdf", "categories": ["earned_leave"]},
                 {"type": "evidence", "label": "https://x/pay.pdf", "categories": ["payroll"]}]}
FRAMED = {"domain": "hr", "answer": "24 days", "sources": ["https://x/earned.pdf", "https://x/pay.pdf"],
          "debug": {"frame_id": "hr.earned_leave", "categories": ["earned_leave"], "fallback_level": 1, "levels_tried": [0, 1],
                    "clarifying_question": None, "query_dag": DAG}}
PLAIN = {"domain": "hr", "answer": "24 days", "sources": ["/tmp/earned.pdf", "/tmp/mix.pdf", "/tmp/unknown.pdf"]}


def test_categories_come_from_the_debug_trace_when_there_is_one():
    cited, origin = smoke.cited_categories(FRAMED, TAX)
    assert cited == [("https://x/earned.pdf", ["earned_leave"]), ("https://x/pay.pdf", ["payroll"])]
    assert "debug trace" in origin


def test_without_a_trace_categories_are_looked_up_in_the_taxonomy_and_say_so():
    cited, origin = smoke.cited_categories(PLAIN, TAX)
    assert cited == [("/tmp/earned.pdf", ["earned_leave"]), ("/tmp/mix.pdf", ["(mixed document)"]),
                     ("/tmp/unknown.pdf", ["uncategorized"])]
    assert "taxonomy lookup" in origin
    assert smoke.cited_categories({"answer": "x", "sources": []}, TAX) == ([], "no citations")


def test_the_summary_reports_frame_categories_fallback_level_clarification_and_cited_categories():
    summary = smoke.summarize("in-domain", "filter", FRAMED, TAX)
    text = smoke.format_summary(summary, "How many days?")
    for expected in ("hr.earned_leave", "['earned_leave']", "fallback_level:   1", "levels tried: [0, 1]",
                     "clarifying asked: no", "cited chunks:     2", "['payroll']", "as expected"):
        assert expected in text


def test_a_clarifying_question_is_shown_and_expected_only_at_full():
    asked = {**FRAMED, "debug": {**FRAMED["debug"], "clarifying_question": "Which leave type?"}, "sources": []}
    full = smoke.summarize("ambiguous", "full", asked, TAX)
    assert full["asked"] and full["matches"] and "YES: Which leave type?" in smoke.format_summary(full, "q")
    assert smoke.summarize("ambiguous", "filter", asked, TAX)["matches"] is False      # filter must not ask
    assert smoke.summarize("ambiguous", "current", asked, TAX)["matches"] is None       # level not named: not judged
    assert smoke.summarize("ambiguous", "full", FRAMED, TAX)["matches"] is False         # full should have asked


def test_the_outside_question_matches_a_refusal_or_no_citations_only():
    refusal = {"domain": "hr", "answer": "I couldn't find enough relevant information in the authorized knowledge base",
               "sources": ["/tmp/earned.pdf"]}
    assert smoke.summarize("outside", "off", refusal, TAX)["matches"] is True
    assert smoke.summarize("outside", "off", {"domain": "hr", "answer": "Canberra", "sources": []}, TAX)["matches"] is True
    assert smoke.summarize("outside", "off", PLAIN, TAX)["matches"] is False


def test_a_paused_answer_is_reported_not_crashed_on():
    body = {"message": "needs review", "status": "paused_for_review", "threadId": "t1"}
    text = smoke.format_summary(smoke.summarize("in-domain", "off", body, TAX), "q")
    assert "paused for human review" in text


def test_run_smoke_sends_the_three_questions_at_every_level_after_switching():
    events, lines = [], []
    questions = {"in-domain": "q1", "ambiguous": "q2", "outside": "q3"}
    code = smoke.run_smoke(lambda q: events.append(("ask", q)) or PLAIN, questions, ["off", "full"],
                           lambda level: events.append(("switch", level)) or True, TAX, lines.append)
    assert code == 0
    assert events == [("switch", "off"), ("ask", "q1"), ("ask", "q2"), ("ask", "q3"),
                      ("switch", "full"), ("ask", "q1"), ("ask", "q2"), ("ask", "q3")]
    assert sum(1 for line in lines if line.startswith("[")) == 6


def test_a_failed_question_is_reported_and_the_rest_still_run():
    lines = []

    def ask(q):
        if q == "q2":
            raise RuntimeError("gateway answered HTTP 429 (rate limit: wait and retry)")
        return PLAIN

    smoke.run_smoke(ask, {"in-domain": "q1", "ambiguous": "q2", "outside": "q3"}, ["off"], None, TAX, lines.append)
    text = "\n".join(lines)
    assert "FAILED: gateway answered HTTP 429" in text and text.count("fallback_level") == 2


def test_a_level_that_cannot_be_set_stops_with_exit_code_1():
    assert smoke.run_smoke(lambda q: PLAIN, {"in-domain": "q"}, ["off"], lambda level: False, TAX, lambda *_: None) == 1


# ---------------------------------------------------------------- environment and unreachable services

def test_without_url_and_token_it_says_what_to_set_and_exits_2(monkeypatch, capsys):
    monkeypatch.delenv("GATEWAY_URL", raising=False)
    monkeypatch.delenv("GATEWAY_TOKEN", raising=False)
    assert smoke.main([]) == 2
    assert "GATEWAY_URL" in capsys.readouterr().out


def test_an_unreachable_gateway_gives_a_clear_message_and_no_traceback(monkeypatch, capsys):
    monkeypatch.setenv("GATEWAY_URL", "http://127.0.0.1:9")          # nothing listens on the discard port
    monkeypatch.setenv("GATEWAY_TOKEN", "secret-token-value")
    assert smoke.main([]) == 2
    out = capsys.readouterr().out
    assert "Cannot reach the gateway at http://127.0.0.1:9" in out and "docker compose up" in out
    assert "Traceback" not in out and "secret-token-value" not in out        # the token is never printed


def test_several_levels_need_a_way_to_switch(monkeypatch, capsys):
    monkeypatch.setenv("GATEWAY_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("GATEWAY_TOKEN", "t")
    assert smoke.main(["--levels", "off", "full"]) == 2
    assert "--switch" in capsys.readouterr().out


def test_nothing_is_hard_coded_for_the_url_or_the_token():
    source = open(smoke.__file__, encoding="utf-8").read()
    assert 'os.getenv("GATEWAY_URL")' in source and 'os.getenv("GATEWAY_TOKEN")' in source
    assert "GATEWAY_URL = " not in source and 'url = "http' not in source
