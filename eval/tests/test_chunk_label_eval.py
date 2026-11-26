"""Tests for eval/chunk_label_eval.py: the metrics, the Wilson interval, the export sample and the score command.

Run from the repo root:  python -m pytest eval/tests -q
The model and the vector index are fakes and the taxonomy is a small one built here: no network, no keys.
"""
import json
import os
import sys
from collections import Counter
from types import SimpleNamespace

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", ".."))
import chunk_label_eval as ev  # noqa: E402
from shared.taxonomy.taxonomy import Category, Taxonomy  # noqa: E402

NAMES = ("leave", "salary", "conduct")
TAX = Taxonomy(categories={"hr": {name: Category("hr", name, f"about {name}", ()) for name in NAMES}},
               documents={"hr": {"big.pdf": NAMES, "small.md": ("leave", "salary"), "single.md": ("leave",)}},
               titles={})


def row(chunk_id, gold, candidates=NAMES, text="text"):
    return {"id": chunk_id, "domain": "hr", "doc": "big.pdf", "candidates": list(candidates), "text": text,
            "gold": list(gold)}


# ---------------------------------------------------------------- the metrics

def test_hit_miss_extra_and_exact_are_counted_apart():
    rows = [row("exact", ["leave"]), row("extra", ["leave"]), row("partial", ["leave", "salary"]),
            row("miss", ["conduct"])]
    result = ev.score(rows, {"exact": ["leave"], "extra": ["leave", "salary"], "partial": ["leave"], "miss": ["salary"]})
    assert result["n"] == 4 and result["hits"] == 2
    assert (result["hit_rate"], result["overlap_rate"], result["exact_rate"]) == (0.5, 0.75, 0.25)
    assert (result["labels_model"], result["labels_gold"], result["labels_baseline"]) == (1.25, 1.25, 3.0)
    assert result["most_missed"] == [("conduct", 1), ("salary", 1)]
    assert result["misses"] == [("partial", ["leave", "salary"], ["leave"]), ("miss", ["conduct"], ["salary"])]


def test_the_full_candidate_list_is_counted():
    result = ev.score([row("a", ["leave"]), row("b", ["leave"])], {"a": list(NAMES), "b": ["leave"]})
    assert result["full_list"] == 1


def test_rows_without_gold_are_skipped_and_reported():
    result = ev.score([row("a", ["leave"]), row("empty", [])], {"a": ["leave"]})
    assert result["n"] == 1 and result["skipped"] == 1


def test_nothing_to_score_gives_no_rates():
    result = ev.score([row("empty", [])], {})
    assert result["n"] == 0 and result["hit_rate"] is None and result["hit_interval"] is None
    assert "1 skipped" in ev.report(result)


@pytest.mark.parametrize("rows, message", [
    ([row("a", ["holidays"])], "not in the candidates"),
    ([row("a", ["conduct"], candidates=("leave", "salary"))], "not in the candidates"),
    ([{**row("a", []), "gold": "leave"}], "must be a list"),
    ([row("a", ["leave"]), row("a", ["leave"])], "appears 2 times"),
])
def test_invalid_gold_is_rejected(rows, message):
    with pytest.raises(ValueError, match=message):
        ev.score(rows, {"a": ["leave"]})


def test_wilson_interval_on_a_known_case():
    low, high = ev.wilson(8, 10)
    assert low == pytest.approx(0.4902, abs=1e-4) and high == pytest.approx(0.9433, abs=1e-4)
    assert ev.wilson(10, 10)[1] == pytest.approx(1.0) and ev.wilson(0, 10)[0] == pytest.approx(0.0)
    assert ev.wilson(0, 0) is None


# ---------------------------------------------------------------- the export sample

class FakeIndex:
    def __init__(self, chunks: dict, reverse=False):
        self.chunks, self.reverse = chunks, reverse

    def list(self, namespace):
        yield sorted(self.chunks, reverse=self.reverse)

    def fetch(self, ids, namespace):
        return SimpleNamespace(vectors={i: SimpleNamespace(metadata=self.chunks[i]) for i in ids})


def stored_chunks():
    chunks = {}
    for source, count in (("big.pdf", 30), ("small.md", 2), ("single.md", 5), ("unlisted.md", 3)):
        for number in range(count):
            chunks[f"{source}-{number:02d}"] = {"source": source, "text": f"text {number}", "categories": ["salary"]}
    chunks["blank"] = {"source": "big.pdf", "text": "  "}
    return chunks


def test_each_document_is_capped_and_single_candidate_documents_are_left_out():
    sample = ev.sample_chunks(FakeIndex(stored_chunks()), TAX, "hr", n=10, seed=7)
    assert Counter(r["doc"] for r in sample) == {"big.pdf": 5, "small.md": 2}      # cap = ceil(10 / 2 documents)
    assert "blank" not in {r["id"] for r in sample}


def test_exported_rows_have_empty_gold_and_no_stored_labels():
    sample = ev.sample_chunks(FakeIndex(stored_chunks()), TAX, "hr", n=4, seed=7)
    assert all(set(r) == {"id", "domain", "doc", "candidates", "text", "gold"} and r["gold"] == [] for r in sample)


def test_the_seed_decides_the_sample_not_the_listing_order():
    def ids(seed, reverse=False):
        return [r["id"] for r in ev.sample_chunks(FakeIndex(stored_chunks(), reverse), TAX, "hr", 10, seed)]

    assert ids(7) == ids(7) == ids(7, reverse=True)
    assert ids(7) != ids(8)


def test_export_does_not_overwrite_an_existing_gold_file(tmp_path, capsys):
    path = tmp_path / "chunk_gold.json"
    path.write_text("hand work", encoding="utf-8")
    assert ev.main(["export", "--namespace", "hr", "--out", str(path)]) == 2
    assert path.read_text(encoding="utf-8") == "hand work" and "already exists" in capsys.readouterr().out


# ---------------------------------------------------------------- the score command

class FakeLLM:
    """Answers each chunk with the labels written in its text; "fail" raises. `later` answers the second run."""

    def __init__(self, later=None):
        self.batches, self.later, self.seen = [], later or {}, Counter()

    def batch(self, messages, config=None, return_exceptions=False):
        self.batches.append(messages)
        answers = []
        for _, (_, text) in messages:
            self.seen[text] += 1
            text = self.later.get(text, text) if self.seen[text] > 1 else text
            answers.append(RuntimeError("boom") if text == "fail" else SimpleNamespace(categories=text.split()))
        return answers


@pytest.fixture
def command(tmp_path, monkeypatch):
    def run(rows, llm, *extra):
        gold = tmp_path / "chunk_gold.json"
        gold.write_text(json.dumps(rows), encoding="utf-8")
        built = []
        monkeypatch.setenv("OPENAI_API_KEY", "fake-secret-key")
        monkeypatch.setenv("LABELING_MODEL", "fake-model")
        monkeypatch.setattr(ev, "load_taxonomy", lambda: TAX)
        monkeypatch.setattr(ev, "build_openai_labeler", lambda model, key: built.append(model) or llm)
        monkeypatch.setattr(ev, "RESULTS_DIR", str(tmp_path / "results"))
        code = ev.main(["score", "--gold", str(gold), *extra])
        stored = list((tmp_path / "results").glob("chunk_label_*.json"))
        return code, built, json.loads(stored[0].read_text(encoding="utf-8")) if stored else None

    return run


def test_score_batches_by_candidates_and_stores_every_chunk(command, capsys):
    rows = [row("a", ["leave"], text="leave"), row("b", ["salary"], text="conduct"),
            row("c", ["leave"], candidates=("leave", "salary"), text="leave salary"), row("d", [], text="leave")]
    llm = FakeLLM()
    code, built, stored = command(rows, llm)
    output = capsys.readouterr().out
    assert code == 0 and built == ["fake-model"]
    assert sorted(len(batch) for batch in llm.batches) == [1, 2]          # the row without gold is never sent
    assert stored["n"] == 3 and stored["skipped"] == 1 and stored["hits"] == 2 and stored["fell_back"] == [0]
    assert {c["id"]: c["got"] for c in stored["chunks"]} == {"a": ["leave"], "b": ["conduct"], "c": ["leave", "salary"]}
    assert "gold-hit rate    66.7%" in output and "('b', ['salary'], ['conduct'])" in output
    assert "fake-secret-key" not in output and "fake-secret-key" not in json.dumps(stored)


def test_the_chunk_text_is_not_printed_or_stored(command, capsys):
    _, _, stored = command([row("a", ["salary"], text="leave confidential-words")], FakeLLM())
    assert "confidential-words" not in capsys.readouterr().out + json.dumps(stored)


def test_repeat_reports_the_share_of_chunks_that_changed(command, capsys):
    rows = [row("a", ["leave"], text="leave"), row("b", ["leave"], text="leave salary")]
    code, _, stored = command(rows, FakeLLM(later={"leave": "salary"}), "--repeat", "2")
    assert code == 0 and stored["changed_between_runs"] == 0.5 and stored["hit_rate"] == 1.0
    assert stored["chunks"][0]["got_second_run"] == ["salary"]
    assert "differ between the two runs: 50.0%" in capsys.readouterr().out


def test_fallbacks_are_reported_and_a_run_of_only_fallbacks_fails(command, capsys):
    code, _, stored = command([row("a", ["leave"], text="fail"), row("b", ["leave"], text="nonsense")], FakeLLM())
    assert code == 1 and stored["fell_back"] == [2] and stored["full_list"] == 2
    assert "do not measure the model" in capsys.readouterr().out


def test_invalid_gold_stops_before_the_model_is_built(command, capsys):
    code, built, stored = command([row("a", ["holidays"])], FakeLLM())
    assert code == 2 and built == [] and stored is None
    assert "not in the candidates" in capsys.readouterr().out
