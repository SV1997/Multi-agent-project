"""Tests for scripts/handcheck.py: sampling and the sheet. No network; a fake index supplies the passage text.

Run from the repo root:  uv run python -m pytest scripts/tests -q
"""
import csv
import os
import sys
from collections import Counter
from types import SimpleNamespace


sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import handcheck  # noqa: E402

COUNTS = {"hr": 25, "legal": 40, "support": 3}
OVERRIDES = {f"{d}-{i}": {"domain": d, "categories": ["c"]} for d, n in COUNTS.items() for i in range(n)}


def domains(ids):
    return Counter(OVERRIDES[i]["domain"] for i in ids)


def test_stratify_takes_n_per_domain_and_all_of_a_small_domain():
    ids = handcheck.pick_stratified(OVERRIDES, 10)
    assert domains(ids) == {"hr": 10, "legal": 10, "support": 3}
    assert len(set(ids)) == len(ids)


def test_stratify_is_repeatable_and_depends_on_the_seed():
    assert handcheck.pick_stratified(OVERRIDES, 10, seed=7) == handcheck.pick_stratified(OVERRIDES, 10, seed=7)
    assert handcheck.pick_stratified(OVERRIDES, 10, seed=7) != handcheck.pick_stratified(OVERRIDES, 10, seed=8)


def test_stratify_lists_domains_in_alphabetical_order():
    ids = handcheck.pick_stratified(OVERRIDES, 2)
    assert [OVERRIDES[i]["domain"] for i in ids] == ["hr", "hr", "legal", "legal", "support", "support"]


def test_the_original_sampling_is_unchanged():
    ids = handcheck.pick_sample(OVERRIDES, 30)
    assert len(ids) == 30 and ids == handcheck.pick_sample(OVERRIDES, 30, seed=7)
    assert ids == sorted(ids, key=ids.index)                     # same call, same order
    assert handcheck.pick_sample(OVERRIDES, 1000) and len(handcheck.pick_sample(OVERRIDES, 1000)) == len(OVERRIDES)


def test_the_parser_defaults_to_the_old_behaviour_and_stratify_defaults_to_ten():
    parse = handcheck.build_parser().parse_args
    assert parse([]).stratify is None and parse([]).seed == 7
    assert parse(["--sample", "30"]).stratify is None
    assert parse(["--stratify"]).stratify == 10
    assert parse(["--stratify", "15"]).stratify == 15


def test_stratified_sheet_leaves_ok_and_note_empty(tmp_path):
    class FakeIndex:
        def fetch(self, ids, namespace):
            return SimpleNamespace(vectors={i: SimpleNamespace(metadata={"text": f"passage {i}"}) for i in ids})

    ids = handcheck.pick_stratified(OVERRIDES, 4)
    out = tmp_path / "sheet.csv"
    handcheck.write_sheet(FakeIndex(), OVERRIDES, ids, str(out))

    rows = list(csv.DictReader(open(out, encoding="utf-8-sig")))
    assert len(rows) == len(ids) == 4 + 4 + 3
    assert all(r["ok (y/n)"] == "" and r["note"] == "" for r in rows)       # never filled in by code
    assert all(r["text"].startswith("passage") for r in rows)


def test_scoring_ignores_unfilled_rows(tmp_path):
    path = tmp_path / "s.csv"
    path.write_text("chunk_id,domain,assigned,ok (y/n),note,text\na,hr,c,y,,t\nb,hr,c,n,why,t\nc,hr,c,,,t\n", encoding="utf-8-sig")
    result = handcheck.score(str(path))
    assert (result["rows"], result["answered"], result["correct"], result["accuracy"]) == (3, 2, 1, 0.5)
