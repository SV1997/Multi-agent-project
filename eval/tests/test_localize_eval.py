"""Tests for eval/localize_eval.py: the question file, the precise/coarse split, and both modes' tables.

Run from the repo root:  python -m pytest eval/tests -q
The model and the orchestrator are fakes; the taxonomy and the frames are the real ones.
"""
import json
import os
import sys
from types import SimpleNamespace

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", ".."))
import localize_eval as ev  # noqa: E402
from shared.taxonomy.taxonomy import Category  # noqa: E402

TAX = ev.load_taxonomy()
HANDBOOK = "tmp5jdxnb7a.pdf"          # 16 categories, includes casual_and_sick_leave
FACILITIES = "tmpueqswgxe.md"         # 1 category, not a leave document


def row(split="tune", domain="hr", category="casual_and_sick_leave", question="q"):
    return {"question": question, "domain": domain, "expected_category": category, "split": split}


@pytest.fixture
def question_file(tmp_path):
    def write(*rows, raw=None):
        path = tmp_path / "questions.jsonl"
        path.write_text("\n".join(raw if raw is not None else [json.dumps(r) for r in rows]), encoding="utf-8")
        return str(path)
    return write


# ---------------------------------------------------------------- the question file

def test_a_valid_file_with_both_splits_is_loaded(question_file):
    rows = ev.load_questions(question_file(row("tune"), row("test", question="q2")), TAX)
    assert [r["split"] for r in rows] == ["tune", "test"]


def test_the_shipped_example_file_is_valid_and_every_row_is_marked_as_an_example():
    rows = ev.load_questions(os.path.join(HERE, "..", "questions.example.jsonl"), TAX)
    assert len(rows) == 5 and all(r["question"].startswith("EXAMPLE") for r in rows)


def test_a_file_with_only_one_split_is_refused(question_file):
    with pytest.raises(ValueError, match="both 'tune' and 'test'"):
        ev.load_questions(question_file(row("tune"), row("tune", question="q2")), TAX)


@pytest.mark.parametrize("bad, message", [
    (row(split="held-out"), "line 1: split must be"),
    (row(domain="sales"), "line 1: 'casual_and_sick_leave' is not a category of 'sales'"),
    (row(category="nonsense"), "line 1: 'nonsense' is not a category of 'hr'"),
    ({**row(), "colour": "red"}, "line 1: the fields must be exactly"),
    ({"question": "q"}, "line 1: the fields must be exactly"),
])
def test_a_bad_line_is_refused_with_its_line_number(question_file, bad, message):
    with pytest.raises(ValueError) as error:
        ev.load_questions(question_file(bad, row("test")), TAX)
    assert message in str(error.value)


def test_bad_json_is_reported_with_its_line_number(question_file):
    with pytest.raises(ValueError, match="line 2: not valid JSON"):
        ev.load_questions(question_file(raw=[json.dumps(row()), "{not json"]), TAX)


# ---------------------------------------------------------------- precise or coarse

def test_a_category_in_a_many_category_handbook_is_coarse():
    assert ev.label_precision(TAX, "hr", "casual_and_sick_leave") == "coarse"


def test_a_parent_is_judged_by_the_documents_of_its_children():
    assert "leave" not in TAX.documents["hr"][HANDBOOK]          # no document lists the parent itself
    assert ev.label_precision(TAX, "hr", "leave") == "coarse"


def test_a_category_only_in_small_documents_is_precise():
    assert ev.label_precision(TAX, "engineering", "container_build_practices") == "precise"
    assert ev.label_precision(TAX, "support", "customer_support_practice") == "precise"


def test_a_category_no_document_carries_has_its_own_group():
    tax = SimpleNamespace(categories={"hr": {"orphan": Category("hr", "orphan", "d", ())}}, documents={"hr": {}})
    assert ev.label_precision(tax, "hr", "orphan") == "no document"


# ---------------------------------------------------------------- mode 1: frames

def pick(frame_id):
    """A fake frame choice: always the frame with this id (or no frame at all for None)."""
    def choose(frames, domain, question):
        return next((f for f in frames if f.frame_id == frame_id), None)
    return choose


def test_a_frame_naming_the_parent_hits_a_child_category_through_the_dag():
    record = ev.frame_records([row(category="earned_leave")], TAX, pick("hr.leave_overview"))[0]
    assert record["hit"] is True and record["searched"] == 5          # leave plus its four children


def test_the_right_frame_hits_and_the_wrong_frame_misses():
    assert ev.frame_records([row(category="earned_leave")], TAX, pick("hr.leave_entitlement"))[0]["hit"] is True
    assert ev.frame_records([row(category="earned_leave")], TAX, pick("hr.provident_fund"))[0]["hit"] is False


def test_no_frame_counts_as_a_miss_but_searches_the_whole_domain():
    record = ev.frame_records([row()], TAX, pick(None))[0]
    assert record["no_frame"] is True and record["hit"] is False and record["searched"] == len(TAX.categories["hr"])


def test_the_frames_table_has_separate_precise_and_coarse_rows_for_each_split():
    rows = [row("tune"), row("test"), row("tune", "engineering", "container_build_practices"),
            row("test", "engineering", "container_build_practices")]
    text = ev.table(ev.frame_records(rows, TAX, pick(None)), ev.FRAME_COLUMNS)
    for split in ("tune", "test"):
        assert f"| {split} | precise | 1 |" in text and f"| {split} | coarse | 1 |" in text
    assert "no document" not in text


def test_an_empty_group_shows_n_a_instead_of_a_misleading_zero():
    text = ev.table(ev.frame_records([row("tune"), row("test")], TAX, pick(None)), ev.FRAME_COLUMNS)
    assert "| tune | precise | 0 | n/a | 0 | n/a |" in text


# ---------------------------------------------------------------- mode 2: answers

def answers(rows, results):
    return ev.answer_records(rows, results, TAX)


def test_a_cited_document_of_another_category_is_outside_and_a_covering_handbook_is_inside():
    record = answers([row(question="1")], [{"question": "1", "sources": [f"/tmp/{FACILITIES}", f"/tmp/{HANDBOOK}"]}])[0]
    assert (record["outside"], record["judged"], record["unjudged"]) == (1, 2, 0)


def test_a_source_the_yaml_does_not_know_is_unjudged_and_repeats_count_once():
    record = answers([row(question="1")], [{"question": "1", "sources": ["/tmp/unknown.pdf", "/tmp/unknown.pdf"]}])[0]
    assert (record["outside"], record["judged"], record["unjudged"]) == (0, 0, 1)


def test_a_coarse_handbook_can_never_be_outside_a_category_it_lists():
    # the finding: whatever HR leave category was expected, citing the 16-category handbook is always "inside"
    for category in ("earned_leave", "casual_and_sick_leave", "leave", "family_leave"):
        record = answers([row(category=category, question="1")], [{"question": "1", "sources": [f"/tmp/{HANDBOOK}"]}])[0]
        assert record["outside"] == 0


def test_a_failed_question_is_flagged_and_results_for_another_file_are_refused():
    assert answers([row(question="1")], [{"question": "1", "error": "TimeoutError"}])[0]["failed"] is True
    with pytest.raises(ValueError, match="different question file"):
        answers([row(question="a")], [{"question": "b", "sources": []}])


def test_the_answers_table_reports_outside_share_failures_and_unjudged_per_group():
    rows = [row("tune", question="1"), row("test", question="2"), row("tune", question="3")]
    results = [{"question": "1", "sources": [f"/tmp/{FACILITIES}", f"/tmp/{HANDBOOK}"]},
               {"question": "2", "sources": ["/tmp/unknown.pdf"]}, {"question": "3", "error": "TimeoutError"}]
    text = ev.table(answers(rows, results), ev.ANSWER_COLUMNS)
    assert "| tune | coarse | 2 | 1 | 2 | 50% | 0 |" in text           # one failed, two judged sources, one outside
    assert "| test | coarse | 1 | 0 | 0 | n/a | 1 |" in text


def test_run_answers_records_a_failure_without_losing_the_other_questions(monkeypatch):
    replies = iter([{"sources": ["a.pdf"]}, RuntimeError("timeout")])

    def fake_get_json(url, body=None, secret=None):
        reply = next(replies)
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setattr(ev, "get_json", fake_get_json)
    results = ev.run_answers([row(question="1"), row(question="2")], "http://x", "secret", "a@b.c")
    assert results[0] == {"question": "1", "sources": ["a.pdf"]}
    assert results[1]["question"] == "2" and "RuntimeError: timeout" in results[1]["error"]


# ---------------------------------------------------------------- the command line

def stack(monkeypatch, tmp_path, localize):
    """A fake stack that reports `localize` on /health and cites one document for every question."""
    monkeypatch.setenv("INTERNAL_SHARED_SECRET", "secret")
    monkeypatch.setattr(ev, "results_path", lambda setting: str(tmp_path / f"answers_{setting}.json"))
    monkeypatch.setattr(ev, "get_json", lambda url, body=None, secret=None:
                        {"localize": localize} if url.endswith("/health") else {"sources": [f"/tmp/{HANDBOOK}"]})


def test_answers_refuses_a_stack_running_with_the_other_setting(monkeypatch, tmp_path, question_file, capsys):
    stack(monkeypatch, tmp_path, "off")
    path = question_file(row("tune"), row("test", question="q2"))
    assert ev.main(["answers", "--questions", path, "--setting", "on"]) == 2
    assert "running with LOCALIZE=off, not on" in capsys.readouterr().out and not list(tmp_path.glob("answers_*"))


def test_answers_stores_one_file_per_setting_and_report_prints_both(monkeypatch, tmp_path, question_file, capsys):
    path = question_file(row("tune"), row("test", question="q2"))
    for setting in ("on", "off"):
        stack(monkeypatch, tmp_path, setting)
        assert ev.main(["answers", "--questions", path, "--setting", setting]) == 0
    capsys.readouterr()
    assert ev.main(["report", "--questions", path]) == 0
    text = capsys.readouterr().out
    assert "LOCALIZE=on" in text and "LOCALIZE=off" in text and "| tune | coarse | 1 |" in text


def test_report_without_stored_results_says_what_to_run(monkeypatch, tmp_path, question_file, capsys):
    monkeypatch.setattr(ev, "results_path", lambda setting: str(tmp_path / f"answers_{setting}.json"))
    assert ev.main(["report", "--questions", question_file(row("tune"), row("test", question="q2"))]) == 2
    assert "--setting on" in capsys.readouterr().out


def test_answers_mode_needs_a_setting_and_the_secret(monkeypatch, question_file, capsys):
    monkeypatch.delenv("INTERNAL_SHARED_SECRET", raising=False)
    assert ev.main(["answers", "--questions", question_file(row("tune"), row("test", question="q2"))]) == 2
    assert "--setting" in capsys.readouterr().out


def test_an_unreachable_service_is_a_message_not_a_traceback(monkeypatch, question_file, capsys):
    monkeypatch.setenv("INTERNAL_SHARED_SECRET", "secret")
    monkeypatch.setattr(ev, "get_json", lambda *a, **k: (_ for _ in ()).throw(ConnectionRefusedError("down")))
    assert ev.main(["answers", "--questions", question_file(row("tune"), row("test", question="q2")), "--setting", "on"]) == 2
    assert "cannot reach" in capsys.readouterr().out


def test_a_bad_question_file_stops_every_mode(question_file, capsys):
    assert ev.main(["frames", "--questions", question_file(row("tune"))]) == 2
    assert "both 'tune' and 'test'" in capsys.readouterr().out
