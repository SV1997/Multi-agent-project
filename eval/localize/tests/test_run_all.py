"""Tests for run-all, the combined comparison table, the split rule, failure handling and the dry run.
Run from the repository root:  uv run python -m pytest eval/localize/tests

Everything uses a fake client or made-up results. The numbers say nothing about the real system.
"""
import csv
import io
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", "..", ".."))
import comparison  # noqa: E402
import fakes  # noqa: E402
import metrics  # noqa: E402
import questions  # noqa: E402
import runner  # noqa: E402
from test_localize_eval import TAX, row, line  # noqa: E402

EXAMPLE = os.path.join(HERE, "..", "questions.example.jsonl")
CATEGORIES = [["earned_leave"], ["sick_leave"], ["payroll"], ["earned_leave", "sick_leave"]]


def many_rows(n=24):
    return [row(f"q{i}", "tune" if i % 2 == 0 else "heldout", CATEGORIES[i % 4], frame=f"hr.{CATEGORIES[i % 4][0]}",
                clarify=i % 3 == 0) for i in range(n)]


# ---------------------------------------------------------------- the split rule

def test_a_set_with_only_one_split_is_refused_with_a_clear_message():
    only_tune = questions.parse_questions([line(id="a"), line(id="b")], TAX)
    with pytest.raises(questions.QuestionError) as error:
        questions.require_both_splits(only_tune)
    text = str(error.value)
    assert '"tune"' in text and '"heldout"' in text and "tune=2, heldout=0" in text


def test_a_row_without_a_split_field_says_what_to_add():
    bad = json.loads(line())
    del bad["split"]
    with pytest.raises(questions.QuestionError) as error:
        questions.parse_questions([json.dumps(bad)], TAX)
    assert "missing field 'split'" in str(error.value) and "tune" in str(error.value)


@pytest.mark.parametrize("command", [["run", "--level", "off"], ["run-all", "--dry-run"], ["report"]])
def test_every_command_refuses_a_set_without_both_splits(tmp_path, monkeypatch, capsys, command):
    monkeypatch.setenv("INTERNAL_SHARED_SECRET", "s")
    path = tmp_path / "q.jsonl"
    path.write_text(line(id="a") + "\n" + line(id="b") + "\n", encoding="utf-8")
    assert runner.main(command + ["--questions", str(path), "--out-dir", str(tmp_path / "out")]) == 2
    assert 'AND rows with "split": "heldout"' in capsys.readouterr().out
    assert not (tmp_path / "out").exists()                                       # nothing was run or written


# ---------------------------------------------------------------- failures are recorded, never skipped

def test_a_failed_question_is_stored_named_on_the_console_and_counted_in_the_table(tmp_path, capsys):
    rows = many_rows(4)

    def make_ask(level):
        def ask(r):
            if r["id"] == "q1":
                raise TimeoutError("read timed out")
            if r["id"] == "q2":
                raise RuntimeError("HTTP 500")
            return {"answer": "a", "sources": [], "debug": None}
        return ask

    reports = runner.run_all(rows, TAX, ["off"], make_ask, None, str(tmp_path), "fp")
    out = capsys.readouterr().out
    assert "2 of 4 questions FAILED at level off" in out
    assert "q1: TimeoutError: read timed out" in out and "q2: RuntimeError: HTTP 500" in out

    stored = json.load(open(tmp_path / "off.json", encoding="utf-8"))["results"]
    assert set(stored) == {"q0", "q1", "q2", "q3"} and "error" in stored["q1"] and "error" in stored["q2"]
    assert reports[0]["errors"] == 2 and reports[0]["all"]["failed"] == 2
    assert reports[0]["tune"]["failed"] == 1 and reports[0]["heldout"]["failed"] == 1    # q2 is tune, q1 is heldout
    failed_row = next(c for t, label, c in comparison.table_rows(reports)
                      if t == "ALL QUESTIONS" and label == "requests that failed")
    assert failed_row == [("count", 2, None)]


def test_a_question_with_no_stored_result_counts_as_failed():
    report = metrics.compute(many_rows(4), {}, TAX, "off")
    assert report["all"]["failed"] == 4 and report["all"]["questions"] == 0


# ---------------------------------------------------------------- the fallback level shares

def test_the_share_at_each_fallback_level_is_over_framed_questions_only():
    rows = [row(f"r{i}", "tune" if i < 3 else "heldout", ["earned_leave"], "hr.earned_leave") for i in range(5)]
    results = {
        "r0": {"debug": {"frame_id": "x", "fallback_level": 0}}, "r1": {"debug": {"frame_id": "x", "fallback_level": 0}},
        "r2": {"debug": {"frame_id": "x", "fallback_level": 2}}, "r3": {"debug": {"frame_id": "x", "fallback_level": None}},
        "r4": {"debug": None},                                                    # no frame: not in the base
    }
    report = metrics.compute(rows, results, TAX, "filter")["all"]
    shares = report["fallback_levels"]
    assert (shares["0"]["count"], shares["1"]["count"], shares["2"]["count"], shares["unrecorded"]["count"]) == (2, 0, 1, 1)
    assert all(s["n"] == 4 for s in shares.values())
    assert report["fallback_rate"]["count"] == 1                                  # only level 2 is "widened" here


def test_at_off_the_level_shares_are_not_available_rather_than_zero():
    results = {f"q{i}": {"debug": None, "sources": []} for i in range(4)}
    shares = metrics.compute(many_rows(4), results, TAX, "off")["all"]["fallback_levels"]
    assert all(s["value"] is None and s["n"] == 0 for s in shares.values())


# ---------------------------------------------------------------- the combined table

def make_reports(tmp_path, fake=True, n=24):
    rows = many_rows(n)
    return rows, runner.run_all(rows, TAX, list(runner.LEVELS), lambda level: fakes.FakeClient(level, TAX), None,
                                str(tmp_path), "fp", fake=fake)


def test_run_all_writes_one_result_file_per_level_and_all_levels_are_reported(tmp_path):
    rows, reports = make_reports(tmp_path)
    assert [r["level"] for r in reports] == ["off", "filter", "prompt", "full"]
    for level in runner.LEVELS:
        data = json.load(open(tmp_path / f"{level}.json", encoding="utf-8"))
        assert data["level"] == level and data["fake"] is True and set(data["results"]) == {r["id"] for r in rows}


def test_the_table_has_every_required_row_for_every_level(tmp_path):
    _, reports = make_reports(tmp_path)
    labels = {label for _, label, _ in comparison.table_rows(reports)}
    for needed in ("wrong-category citations", "frame accuracy", "clarification correct", "fallback (widened) rate",
                   "answered at level 0 (frame's categories)", "answered at level 1 (parents' family)",
                   "answered at level 2 (whole domain)", "requests that failed"):
        assert needed in labels
    sections = {title.split(" (")[0] for title, _, _ in comparison.table_rows(reports)}
    assert {"ALL QUESTIONS", "TUNE QUESTIONS", "HELD-OUT QUESTIONS", "GAP"} <= sections           # the tune vs held-out gap
    assert all(len(cells) == 4 for _, _, cells in comparison.table_rows(reports))


def test_csv_and_markdown_are_written_together_and_agree(tmp_path):
    _, reports = make_reports(tmp_path)
    csv_path, md_path = comparison.write_comparison(reports, str(tmp_path), banner=runner.DRYRUN_BANNER)

    table = list(csv.reader(io.StringIO(open(csv_path, encoding="utf-8-sig").read())))
    assert table[0] == ["section", "metric", "off", "off_n", "filter", "filter_n", "prompt", "prompt_n", "full", "full_n"]
    by_key = {(r[0], r[1]): r for r in table[1:]}
    assert by_key[("ALL QUESTIONS", "frame accuracy")][2:4] == ["", "0"]              # off: no value (n/a), measured on 0 questions - never a 0 rate
    assert by_key[("ALL QUESTIONS", "frame accuracy")][4] != ""                       # filter has a value

    md = open(md_path, encoding="utf-8").read()
    assert md.startswith("**DRY RUN") and "| | off | filter | prompt | full |" in md
    assert "| frame accuracy | n/a |" in md and "## Gap" in md
    assert len(md.splitlines()) > 40


def test_a_real_table_has_no_dry_run_banner(tmp_path):
    _, reports = make_reports(tmp_path, fake=False)
    _, md_path = comparison.write_comparison(reports, str(tmp_path))
    assert "DRY RUN" not in open(md_path, encoding="utf-8").read()


def test_report_command_rewrites_the_table_and_marks_fake_runs(tmp_path):
    path = tmp_path / "q.jsonl"
    path.write_text("\n".join([line(id="a", split="tune"), line(id="b", split="heldout")]) + "\n", encoding="utf-8")
    out = tmp_path / "out"
    assert runner.main(["run-all", "--dry-run", "--questions", str(path), "--out-dir", str(out)]) == 0
    os.remove(out / "comparison.md")
    assert runner.main(["report", "--questions", str(path), "--out-dir", str(out)]) == 0
    assert open(out / "comparison.md", encoding="utf-8").read().startswith("**DRY RUN")


# ---------------------------------------------------------------- the fake client

def _try(client, r):
    try:
        return client(r)
    except TimeoutError:
        return None


def test_the_fake_client_is_repeatable_and_off_carries_no_frame():
    rows = many_rows()
    first = [_try(fakes.FakeClient("full", TAX), r) for r in rows]
    assert first == [_try(fakes.FakeClient("full", TAX), r) for r in rows]
    off = [_try(fakes.FakeClient("off", TAX), r) for r in rows]
    assert all(x is None or x["debug"] is None for x in off)
    assert any(x is None for x in first) and any(x and x["debug"] for x in first)        # some fail, some are framed
    assert all("FAKE" in x["answer"] for x in first if x)


# ---------------------------------------------------------------- the command line

def test_the_dry_run_command_needs_no_secret_or_services(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("INTERNAL_SHARED_SECRET", raising=False)
    monkeypatch.setattr(runner, "post_query", lambda *a, **k: pytest.fail("a dry run must not touch the network"))
    assert runner.main(["run-all", "--dry-run", "--questions", EXAMPLE, "--out-dir", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert runner.DRYRUN_BANNER in out and "ALL QUESTIONS" in out
    for name in ("off.json", "filter.json", "prompt.json", "full.json", "comparison.csv", "comparison.md"):
        assert (tmp_path / name).exists()


def test_the_dry_run_does_not_write_into_the_real_results_folder():
    assert runner.DRYRUN_DIR != runner.RESULTS_DIR and runner.DRYRUN_DIR.endswith("results_dryrun")


def test_a_live_run_all_needs_the_secret_and_a_way_to_switch_levels(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("INTERNAL_SHARED_SECRET", raising=False)
    assert runner.main(["run-all", "--questions", EXAMPLE, "--out-dir", str(tmp_path)]) == 2
    monkeypatch.setenv("INTERNAL_SHARED_SECRET", "s")
    assert runner.main(["run-all", "--questions", EXAMPLE, "--out-dir", str(tmp_path)]) == 2
    assert "--switch compose" in capsys.readouterr().out and not os.listdir(tmp_path)


def test_a_live_run_all_switches_the_stack_before_each_level_in_order(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERNAL_SHARED_SECRET", "s")
    order = []
    monkeypatch.setattr(runner, "switch_with_compose", lambda level, url: order.append(("switch", level)) or True)
    monkeypatch.setattr(runner, "post_query", lambda url, secret, r, email, timeout=180:
                        order.append(("ask", r["id"])) or {"answer": "a", "sources": [], "debug": None})

    assert runner.main(["run-all", "--switch", "compose", "--questions", EXAMPLE, "--out-dir", str(tmp_path)]) == 0
    assert [x[1] for x in order if x[0] == "switch"] == ["off", "filter", "prompt", "full"]
    assert order[0] == ("switch", "off") and order[1][0] == "ask"                      # switched first, then asked
    assert (tmp_path / "comparison.csv").exists() and not runner.stored_as_fake(str(tmp_path))


def test_a_failed_switch_stops_the_run_but_keeps_the_levels_already_stored(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("INTERNAL_SHARED_SECRET", "s")
    monkeypatch.setattr(runner, "switch_with_compose", lambda level, url: level != "prompt")
    monkeypatch.setattr(runner, "post_query", lambda *a, **k: {"answer": "a", "sources": [], "debug": None})

    assert runner.main(["run-all", "--switch", "compose", "--questions", EXAMPLE, "--out-dir", str(tmp_path)]) == 0
    assert sorted(f for f in os.listdir(tmp_path) if f.endswith(".json")) == ["filter.json", "off.json"]
    assert "Could not switch the stack to LOCALIZE=prompt" in capsys.readouterr().out
