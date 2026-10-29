"""Tests for the localization evaluation: question set format, the metrics, and the runner. No network, no services.
Run from the repository root:  python -m pytest eval/localize/tests

The metric tests use a small taxonomy and results made up on the spot, with the expected numbers worked out by hand
in the comments. Nothing here says anything about how well the real system does - that comes only from running it.
"""
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", "..", ".."))
import metrics  # noqa: E402
import questions  # noqa: E402
import runner  # noqa: E402
from shared.taxonomy.taxonomy import parse_taxonomy, load_taxonomy  # noqa: E402

TAX = parse_taxonomy({"hr": {
    "categories": {
        "leave": {"description": "All leave", "parents": []},
        "earned_leave": {"description": "Earned leave", "parents": ["leave"]},
        "sick_leave": {"description": "Sick leave", "parents": ["leave"]},
        "payroll": {"description": "Pay", "parents": []},
    },
    "documents": {"earned.pdf": ["earned_leave"], "sick.pdf": ["sick_leave"], "pay.pdf": ["payroll"]},
}})


def row(id_, split, expected_categories, frame=None, clarify=False, domain="hr"):
    return {"id": id_, "split": split, "domain": domain, "question": f"question {id_}", "expected_frame": frame,
            "expected_categories": expected_categories, "needs_clarification": clarify, "reference_answer": ""}


def line(**changes):
    return json.dumps({**row("q1", "tune", ["earned_leave"], "hr.earned_leave"), **changes})


# ---------------------------------------------------------------- the question set

def test_a_valid_set_is_loaded():
    rows = questions.parse_questions([line(), "", "# a comment", line(id="q2", split="heldout")], TAX)
    assert [r["id"] for r in rows] == ["q1", "q2"]


@pytest.mark.parametrize("changes, message", [
    ({"split": "held-out"}, "split must be one of"),
    ({"domain": "sales"}, "unknown domain"),
    ({"expected_categories": ["nonsense"]}, "not in the hr taxonomy"),
    ({"expected_frame": "legal.x"}, "must be null or an id starting with 'hr.'"),
    ({"needs_clarification": "yes"}, "needs_clarification must be true or false"),
    ({"question": "  "}, "question must be non-empty"),
    ({"reference_answer": None}, "reference_answer must be text"),
])
def test_a_bad_row_is_refused_with_its_line_number(changes, message):
    with pytest.raises(questions.QuestionError) as error:
        questions.parse_questions([line(**changes)], TAX)
    assert "line 1" in str(error.value) and message in str(error.value)


def test_missing_and_unknown_fields_duplicates_and_bad_json_are_all_reported_together():
    broken = json.dumps({"id": "a", "split": "tune"})
    extra = json.dumps({**row("b", "tune", []), "colour": "red"})
    with pytest.raises(questions.QuestionError) as error:
        questions.parse_questions([broken, extra, line(), line(), "{not json"], TAX)
    text = str(error.value)
    for part in ("line 1: missing field 'domain'", "line 2: unknown field 'colour'", "line 4: id 'q1' is used twice", "line 5: not valid JSON"):
        assert part in text


def test_an_expected_frame_must_be_in_the_menu_when_the_menu_is_known():
    questions.parse_questions([line()], TAX, known_frames={"hr.earned_leave"})
    with pytest.raises(questions.QuestionError, match="not in the frame menu"):
        questions.parse_questions([line()], TAX, known_frames={"hr.other"})


def test_the_shipped_example_file_has_exactly_three_marked_rows_against_the_real_taxonomy_and_frames():
    taxonomy = load_taxonomy()
    rows = questions.load_questions(os.path.join(HERE, "..", "questions.example.jsonl"), taxonomy, runner.known_frame_ids(taxonomy))
    assert len(rows) == 3 and all(questions.is_example(r) for r in rows)
    assert all(r["question"].startswith("EXAMPLE") and r["reference_answer"] == "" for r in rows)


# ---------------------------------------------------------------- the metrics

ROWS = [
    row("r1", "tune", ["earned_leave"], frame="hr.earned_leave"),
    row("r2", "heldout", ["sick_leave"], frame="hr.sick_leave", clarify=True),
    row("r3", "tune", [], frame=None, clarify=True),
    row("r4", "heldout", ["earned_leave"], frame="hr.earned_leave"),
]
RESULTS = {
    "r1": {"sources": ["http://x/earned.pdf?sig=1", "pay.pdf", "mix.pdf"],
           "debug": {"frame_id": "hr.earned_leave", "fallback_level": 0, "clarifying_question": None}},
    "r2": {"sources": ["sick.pdf", "sick.pdf"],
           "debug": {"frame_id": "hr.other", "fallback_level": 2, "clarifying_question": "Which leave?"}},
    "r3": {"sources": ["pay.pdf"], "debug": None},
    "r4": {"error": "TimeoutError: slow"},
}


def test_wrong_category_citation_counts_distinct_judgeable_sources_only():
    # r1: earned.pdf right, pay.pdf wrong, mix.pdf unjudged (not in the taxonomy).  r2: sick.pdf once (duplicate ignored), right.
    # r3 has no expected categories, so pay.pdf is not counted.  Wrong 1 of 3 judged.
    result = metrics.compute(ROWS, RESULTS, TAX, "full")["all"]["wrong_category_citation"]
    assert (result["count"], result["n"], result["unjudged"]) == (1, 3, 1) and result["value"] == pytest.approx(1 / 3)


def test_frame_accuracy_counts_a_missing_frame_as_wrong_and_ignores_questions_with_no_expected_frame():
    # asked: r1 (right), r2 (hr.other, wrong); r3 expects no frame; r4 failed.  1 of 2.
    result = metrics.compute(ROWS, RESULTS, TAX, "full")["all"]["frame_accuracy"]
    assert (result["count"], result["n"]) == (1, 2)


def test_clarification_correct_compares_asked_with_needed():
    # r1 needs no question, none asked: right.  r2 needs one, asked: right.  r3 needs one, none asked: wrong.  2 of 3.
    result = metrics.compute(ROWS, RESULTS, TAX, "full")["all"]["clarification_correct"]
    assert (result["count"], result["n"]) == (2, 3)


def test_fallback_rate_is_over_questions_that_got_a_frame():
    # r1 level 0 (not widened), r2 level 2 (widened); r3 has no frame.  1 of 2.
    result = metrics.compute(ROWS, RESULTS, TAX, "full")["all"]["fallback_rate"]
    assert (result["count"], result["n"]) == (1, 2)


def test_the_split_and_the_gap():
    report = metrics.compute(ROWS, RESULTS, TAX, "full")
    # tune = r1, r3; heldout = r2 (r4 failed). Wrong-category: tune 1 of 2 (pay.pdf), heldout 0 of 1.
    assert report["tune"]["questions"] == 2 and report["heldout"]["questions"] == 1 and report["errors"] == 1
    assert report["tune"]["wrong_category_citation"]["value"] == 0.5 and report["heldout"]["wrong_category_citation"]["value"] == 0
    assert report["gap"]["wrong_category_citation"] == 0.5
    # frame accuracy: tune 1 of 1, heldout 0 of 1 -> gap 1.0.  clarification: tune 1 of 2, heldout 1 of 1 -> gap -0.5.
    assert report["gap"]["frame_accuracy"] == 1.0 and report["gap"]["clarification_correct"] == -0.5


def test_levels_that_cannot_measure_a_metric_report_not_available_instead_of_zero():
    off = metrics.compute(ROWS, {k: {**v, "debug": None} for k, v in RESULTS.items()}, TAX, "off")
    for name in ("frame_accuracy", "clarification_correct", "fallback_rate"):
        assert off["all"][name]["value"] is None and off["all"][name]["n"] == 0
    assert off["all"]["frame_accuracy"]["value"] is None and off["all"]["clarification_correct"]["value"] is None
    assert off["all"]["fallback_rate"]["value"] is None
    assert off["all"]["wrong_category_citation"]["value"] is not None            # this one needs no debug
    assert off["gap"]["frame_accuracy"] is None
    # below "full" nobody asks clarifying questions, so that metric is not available either
    assert metrics.compute(ROWS, RESULTS, TAX, "prompt")["all"]["clarification_correct"]["value"] is None
    assert metrics.percent(None) == "n/a" and metrics.percent(0.5) == "50.0%"


def test_a_missing_result_counts_as_an_error():
    assert metrics.compute(ROWS, {}, TAX, "off")["errors"] == 4


# ---------------------------------------------------------------- the runner

def test_run_questions_keeps_going_after_a_failure_and_records_it():
    def ask(r):
        if r["id"] == "r2":
            raise TimeoutError("slow")
        if r["id"] == "r3":
            return {"status": "paused_for_review"}
        return {"answer": "a", "sources": ["earned.pdf"], "confidence": 0.9, "debug": {"frame_id": "hr.x"}}
    results = runner.run_questions(ROWS, ask)
    assert set(results) == {"r1", "r2", "r3", "r4"}
    assert results["r2"]["error"] == "TimeoutError: slow" and results["r3"]["error"] == "paused for human review"
    assert results["r1"]["sources"] == ["earned.pdf"] and results["r1"]["debug"] == {"frame_id": "hr.x"}


def test_warnings_when_the_server_is_not_at_the_level_the_user_named():
    framed = {"a": {"debug": {"frame_id": "hr.x"}}}
    plain = {"a": {"debug": None}}
    assert runner.level_warnings(framed, "off") and runner.level_warnings(plain, "full")
    assert runner.level_warnings(framed, "full") == [] and runner.level_warnings(plain, "off") == []
    assert runner.level_warnings({"a": {"error": "x"}}, "full") == []            # nothing answered, nothing to judge


def test_results_are_stored_per_level_and_a_changed_question_set_makes_them_stale(tmp_path, capsys):
    runner.save_results(str(tmp_path), "off", "abc", {"r1": {"sources": []}})
    runner.save_results(str(tmp_path), "full", "OLD", {"r1": {"sources": []}})
    found = runner.load_all_results(str(tmp_path), "abc")
    assert list(found) == ["off"] and "full" in capsys.readouterr().out


def test_the_report_has_one_column_per_level_and_shows_not_available(capsys):
    reports = [metrics.compute(ROWS, {k: {**v, "debug": None} for k, v in RESULTS.items()}, TAX, "off"),
               metrics.compute(ROWS, RESULTS, TAX, "full")]
    text = runner.format_report(reports)
    assert "off" in text and "full" in text and "n/a" in text and "33.3% (n=3)" in text
    assert "GAP" in text and "HELD-OUT QUESTIONS" in text and "requests that failed" in text


def test_the_command_line_runs_and_reports_with_a_fake_orchestrator(tmp_path, monkeypatch, capsys):
    questions_path = os.path.join(HERE, "..", "questions.example.jsonl")
    monkeypatch.setenv("INTERNAL_SHARED_SECRET", "test-secret")
    seen = []

    def fake_post(url, secret, r, email, timeout=180):
        seen.append((url, secret, r["id"]))
        return {"answer": "fake", "sources": [], "confidence": 0.5, "debug": None}
    monkeypatch.setattr(runner, "post_query", fake_post)

    assert runner.main(["run", "--level", "off", "--questions", questions_path, "--out-dir", str(tmp_path)]) == 0
    assert [s[2] for s in seen] == ["EXAMPLE-1", "EXAMPLE-2", "EXAMPLE-3"] and seen[0][1] == "test-secret"
    assert os.path.exists(tmp_path / "off.json")
    out = capsys.readouterr().out
    assert "EXAMPLE rows" in out                                        # the warning that this is not real data

    assert runner.main(["report", "--questions", questions_path, "--out-dir", str(tmp_path)]) == 0
    assert "ALL QUESTIONS" in capsys.readouterr().out


def test_the_command_line_refuses_to_run_without_the_secret_or_with_a_broken_set(tmp_path, monkeypatch, capsys):
    good = os.path.join(HERE, "..", "questions.example.jsonl")
    monkeypatch.delenv("INTERNAL_SHARED_SECRET", raising=False)
    assert runner.main(["run", "--level", "off", "--questions", good, "--out-dir", str(tmp_path)]) == 2
    bad = tmp_path / "bad.jsonl"
    bad.write_text(line(split="nope") + "\n", encoding="utf-8")
    assert runner.main(["report", "--questions", str(bad), "--out-dir", str(tmp_path)]) == 2
    assert "question set is invalid" in capsys.readouterr().out
    assert runner.main(["report", "--questions", good, "--out-dir", str(tmp_path / "empty")]) == 1
