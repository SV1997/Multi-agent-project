"""Tests for scripts/backfill.py with fakes: no network, no database, no real taxonomy file.

Run from the repo root:  uv run python -m pytest scripts/tests -q
"""
import asyncio
import pytest
import os
import pickle
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import backfill
from shared.taxonomy.taxonomy import parse_taxonomy

DATA = {
    "hr": {
        "categories": {
            "leave": {"description": "All leave rules", "parents": []},
            "earned_leave": {"description": "Earned leave", "parents": ["leave"]},
        },
        "documents": {
            "handbook.pdf": {"title": "HR Handbook", "categories": ["leave", "earned_leave"]},
            "other.pdf": ["leave", "earned_leave"],
        },
    },
    "legal": {
        "categories": {
            "privacy": {"description": "Privacy law", "parents": []},
            "non_content": {"description": "Menus and reference lists", "parents": []},
        },
        "documents": {"gdpr": {"title": "GDPR", "categories": ["privacy"]}, "menu.md": ["non_content"]},
    },
}
TAX = parse_taxonomy(DATA)


class FakeIndex:
    """Serverless-style index in memory. list() returns pages of 2 ids so paging is exercised too."""

    def __init__(self, store, fail_ids=()):
        self.store = store                  # namespace -> chunk id -> metadata
        self.fail_ids = set(fail_ids)
        self.update_calls = []

    def list(self, namespace, prefix=""):
        ids = [i for i in self.store.get(namespace, {}) if i.startswith(prefix)]
        for start in range(0, len(ids), 2):
            yield ids[start:start + 2]

    def fetch(self, ids, namespace):
        found = {i: SimpleNamespace(metadata=dict(self.store[namespace][i])) for i in ids if i in self.store[namespace]}
        return SimpleNamespace(vectors=found)

    def update(self, id, set_metadata=None, namespace=None, **kwargs):
        if id in self.fail_ids:
            raise RuntimeError("pinecone said no")
        self.update_calls.append((namespace, id, set_metadata))
        self.store[namespace][id].update(set_metadata)

    def describe_index_stats(self):
        return SimpleNamespace(namespaces={ns: SimpleNamespace(vector_count=len(v)) for ns, v in self.store.items()})


def make_index(**kwargs):
    return FakeIndex({
        "hr": {
            "hr-1": {"source": "/tmp/handbook.pdf", "text": "Earned leave is 24 days", "title": "Old PDF title"},
            "hr-2": {"source": "/tmp/other.pdf", "text": "x"},
            "hr-3": {"source": "/tmp/brand_new.pdf", "text": "y"},
        },
        "legal": {
            "legal-menu": {"source": "https://x.org/menu.md?sig=1", "text": "menu"},
            "legal-text": {"source": "https://x.org/gdpr?sig=1", "text": "Privacy rules"},
        },
        "coding": {"c-1": {"source": "/tmp/other.py", "text": "print(1)"}},
    }, **kwargs)


# ---------------------------------------------------------------- Pinecone side

def test_the_plan_reads_everything_and_writes_nothing():
    index = make_index()
    updates, targets, stats = backfill.plan_pinecone(index, TAX, ["hr", "legal"])

    assert index.update_calls == []                      # a plan never writes
    assert len(updates) == 5 and stats["hr"]["to_update"] == 3 and stats["legal"]["to_update"] == 2
    assert stats["hr"]["chunks"] == 3 and stats["legal"]["chunks"] == 2


def test_the_plan_computes_the_right_fields_for_each_kind_of_chunk():
    updates, _, _ = backfill.plan_pinecone(make_index(), TAX, ["hr", "legal"])
    by_id = {chunk_id: fields for _, chunk_id, fields in updates}

    assert by_id["hr-1"] == {"categories": ["leave", "earned_leave"], "is_content": True,
                             "title": "HR Handbook", "original_title": "Old PDF title"}
    assert by_id["hr-2"] == {"categories": ["leave", "earned_leave"], "is_content": True}   # a document with no title
    assert by_id["hr-3"] == {"categories": ["uncategorized"], "is_content": True}
    assert by_id["legal-menu"] == {"categories": ["non_content"], "is_content": False}
    assert by_id["legal-text"]["categories"] == ["privacy"]


def test_the_report_counts_uncategorized_non_content_and_saved_titles():
    _, _, stats = backfill.plan_pinecone(make_index(), TAX, ["hr", "legal"])

    assert stats["hr"]["uncategorized"] == 1
    assert stats["hr"]["uncategorized_sources"] == {"/tmp/brand_new.pdf": 1}
    assert stats["hr"]["original_title_saved"] == 1
    assert stats["legal"]["non_content"] == 1 and stats["legal"].get("uncategorized", 0) == 0


def test_applying_writes_exactly_the_planned_fields_and_nothing_else():
    index = make_index()
    updates, _, _ = backfill.plan_pinecone(index, TAX, ["hr", "legal"])
    done, failed = backfill.apply_pinecone(index, updates, log=lambda *_: None)

    assert (done, failed) == (5, 0)
    assert index.store["hr"]["hr-1"]["text"] == "Earned leave is 24 days"          # untouched fields stay
    assert index.store["hr"]["hr-1"]["title"] == "HR Handbook"
    assert index.store["hr"]["hr-1"]["original_title"] == "Old PDF title"
    assert index.store["coding"]["c-1"] == {"source": "/tmp/other.py", "text": "print(1)"}   # other namespace untouched


def test_running_twice_changes_nothing_the_second_time():
    index = make_index()
    updates, _, _ = backfill.plan_pinecone(index, TAX, ["hr", "legal"])
    backfill.apply_pinecone(index, updates, log=lambda *_: None)
    calls_after_first_run = len(index.update_calls)

    updates_again, _, stats = backfill.plan_pinecone(index, TAX, ["hr", "legal"])
    done, failed = backfill.apply_pinecone(index, updates_again, log=lambda *_: None)

    assert updates_again == [] and (done, failed) == (0, 0)
    assert len(index.update_calls) == calls_after_first_run
    assert stats["hr"]["already_correct"] == 3 and stats["legal"]["already_correct"] == 2
    assert index.store["hr"]["hr-1"]["original_title"] == "Old PDF title"       # not overwritten by the second pass


def test_one_failing_chunk_does_not_stop_the_others():
    index = make_index(fail_ids=["hr-2"])
    updates, _, _ = backfill.plan_pinecone(index, TAX, ["hr", "legal"])
    logged = []
    done, failed = backfill.apply_pinecone(index, updates, log=logged.append)

    assert (done, failed) == (4, 1)
    assert any("hr-2"[:8] in line and "RuntimeError" in line for line in logged)
    assert "categories" in index.store["legal"]["legal-text"]                    # later chunks were still written


def test_namespaces_outside_the_taxonomy_are_listed_and_never_planned():
    index = make_index()
    assert backfill.skipped_namespaces(index, ("hr", "legal", "finance")) == [("coding", 1)]
    _, _, stats = backfill.plan_pinecone(index, TAX, ["hr", "legal"])
    assert "coding" not in stats


def test_two_chunks_with_the_same_text_but_different_labels_are_reported():
    # same stored source and text, but uploaded under different file names, so the taxonomy labels them differently
    taxonomy = parse_taxonomy({"hr": {
        "categories": {"leave": {"description": "Leave", "parents": []}, "pay": {"description": "Pay", "parents": []}},
        "documents": {"a.pdf": ["leave"], "b.pdf": ["pay"]},
    }})
    index = FakeIndex({"hr": {
        "hr-a": {"source": "/tmp/tmp1.pdf", "file_name": "a.pdf", "text": "same text"},
        "hr-b": {"source": "/tmp/tmp1.pdf", "file_name": "b.pdf", "text": "same text"},
    }})
    _, targets, stats = backfill.plan_pinecone(index, taxonomy, ["hr"])

    assert stats["hr"]["same_text_two_labels"] == 1
    assert targets[("hr", "/tmp/tmp1.pdf", "same text")]["categories"] == ["leave"]     # the first one is kept


# ---------------------------------------------------------------- BM25 side

def hr_bm25_data():
    return {"Bm25": "BM25-OBJECT", "chunks": [
        {"text": "Earned leave is 24 days", "source": "/tmp/handbook.pdf"},     # twin of hr-1
        {"text": "x", "source": "/tmp/other.pdf"},                             # twin of hr-2
        {"text": "orphan text", "source": "/tmp/handbook.pdf"},                # no twin in Pinecone
        "plain old string",
    ]}


def test_bm25_chunks_are_matched_to_their_pinecone_twin_by_source_and_text():
    _, targets, _ = backfill.plan_pinecone(make_index(), TAX, ["hr"])
    original = hr_bm25_data()["chunks"]
    new_chunks, stats = backfill.plan_bm25(original, "hr", TAX, targets)

    assert new_chunks[0]["categories"] == ["leave", "earned_leave"] and new_chunks[0]["title"] == "HR Handbook"
    assert new_chunks[1]["categories"] == ["leave", "earned_leave"]           # found by source and text, like hr-2
    assert new_chunks[2]["categories"] == ["leave", "earned_leave"]           # no twin: the document's labels
    assert new_chunks[3] == "plain old string"
    assert stats == {"chunks": 4, "to_update": 3, "no_pinecone_twin": 1, "plain_string_left_alone": 1}
    assert "categories" not in original[0]                                    # the input list was not changed


def test_a_bm25_chunk_without_twin_in_an_unknown_document_is_counted_uncategorized():
    _, stats = backfill.plan_bm25([{"text": "t", "source": "/tmp/unknown.pdf"}], "hr", TAX, {})
    assert stats["no_pinecone_twin"] == 1 and stats["no_twin_uncategorized"] == 1


class FakeConn:
    """Stands in for the Neon connection: bm25_indexes as {namespace: pickled bytes}."""

    def __init__(self, rows):
        self.rows = rows
        self.saved = []

    async def fetchrow(self, query, namespace):
        return {"indexData": self.rows[namespace]} if namespace in self.rows else None

    async def close(self):
        pass

    async def execute(self, query, namespace, blob, when):
        self.saved.append((namespace, pickle.loads(blob)))
        self.rows[namespace] = blob


def run(coro):
    return asyncio.run(coro)


def test_bm25_dry_run_reads_but_never_saves():
    _, targets, _ = backfill.plan_pinecone(make_index(), TAX, ["hr"])
    conn = FakeConn({"hr": pickle.dumps(hr_bm25_data())})
    results = run(backfill.run_bm25(conn, TAX, targets, ["hr", "legal"], apply=False))

    assert conn.saved == []
    assert results["hr"]["to_update"] == 3
    assert results["legal"] == {"no_index": True}                              # no row stored for legal


def test_bm25_apply_saves_the_labels_and_keeps_the_index_object():
    _, targets, _ = backfill.plan_pinecone(make_index(), TAX, ["hr"])
    conn = FakeConn({"hr": pickle.dumps(hr_bm25_data())})
    run(backfill.run_bm25(conn, TAX, targets, ["hr"], apply=True))

    assert len(conn.saved) == 1
    namespace, data = conn.saved[0]
    assert namespace == "hr" and data["Bm25"] == "BM25-OBJECT"
    assert data["chunks"][1]["categories"] == ["leave", "earned_leave"] and data["chunks"][3] == "plain old string"


def test_bm25_second_run_saves_nothing():
    _, targets, _ = backfill.plan_pinecone(make_index(), TAX, ["hr"])
    conn = FakeConn({"hr": pickle.dumps(hr_bm25_data())})
    run(backfill.run_bm25(conn, TAX, targets, ["hr"], apply=True))
    conn.saved.clear()

    results = run(backfill.run_bm25(conn, TAX, targets, ["hr"], apply=True))
    assert conn.saved == [] and results["hr"].get("to_update", 0) == 0 and results["hr"]["already_correct"] == 3


# ---------------------------------------------------------------- report

def test_the_report_says_dry_run_unless_apply_was_given():
    index = make_index()
    _, _, pine_stats = backfill.plan_pinecone(index, TAX, ["hr"])
    lines = []
    backfill.print_report(pine_stats, {"hr": {"chunks": 4}}, [("coding", 97)], apply=False, log=lines.append)
    text = "\n".join(lines)
    assert "DRY RUN - nothing was written" in text and "coding (97 vectors)" in text and "uncategorized: /tmp/brand_new.pdf" in text

    lines.clear()
    backfill.print_report(pine_stats, {"hr": {"chunks": 4}}, [], apply=True, log=lines.append)
    assert "DRY RUN" not in "\n".join(lines)


# ---------------------------------------------------------------- chunks that carry the uploaded file name (Phase 2)

def test_a_chunk_with_a_file_name_is_matched_to_its_document_in_pinecone_and_bm25():
    signed = "https://files.example.com/bucket/0f8fad5b-d9cb-469f-a165-70867728950e-handbook.pdf?sig=1"
    index = FakeIndex({"hr": {"h#1": {"source": signed, "file_name": "handbook.pdf", "text": "Earned leave"}}})
    updates, targets, stats = backfill.plan_pinecone(index, TAX, ["hr"])

    assert stats["hr"].get("uncategorized", 0) == 0
    assert dict((cid, f) for _, cid, f in updates)["h#1"]["categories"] == ["leave", "earned_leave"]

    bm25_chunk = {"text": "orphan text", "source": signed, "file_name": "handbook.pdf"}
    new_chunks, bm25_stats = backfill.plan_bm25([bm25_chunk], "hr", TAX, targets)
    assert new_chunks[0]["categories"] == ["leave", "earned_leave"]
    assert "no_twin_uncategorized" not in bm25_stats          # the file name found its document, so not uncategorized


# ---------------------------------------------------------------- the command line: dry run by default, no re-embedding

class StrictIndex(FakeIndex):
    """Fails the test if an update tries to send anything but metadata (a vector would mean re-embedding)."""

    def update(self, id, set_metadata=None, namespace=None):
        super().update(id, set_metadata=set_metadata, namespace=namespace)


def make_connect(rows):
    conn = FakeConn(rows)

    async def connect():
        return conn

    return connect, conn


def hr_args(*argv):
    return backfill.build_parser().parse_args(list(argv))


def test_the_default_is_a_dry_run_and_apply_must_be_asked_for():
    assert backfill.build_parser().parse_args([]).apply is False
    assert backfill.build_parser().parse_args([]).report_orphans is False
    assert backfill.build_parser().parse_args(["--apply"]).apply is True


def test_a_dry_run_through_execute_writes_to_neither_pinecone_nor_neon():
    index = StrictIndex(make_index().store)
    connect, conn = make_connect({"hr": pickle.dumps(hr_bm25_data())})
    lines = []
    failed = backfill.execute(hr_args("--namespace", "hr"), TAX, index, connect, lines.append)

    assert failed == 0 and index.update_calls == [] and conn.saved == []
    assert "DRY RUN - nothing was written" in "\n".join(lines)


def test_apply_updates_metadata_only_and_the_bm25_pickle_and_a_second_apply_finds_nothing_to_do():
    index = StrictIndex(make_index().store)                  # update() accepts no vector argument at all
    connect, conn = make_connect({"hr": pickle.dumps(hr_bm25_data())})

    first = []
    assert backfill.execute(hr_args("--apply", "--namespace", "hr"), TAX, index, connect, first.append) == 0
    assert len(index.update_calls) == 3 and all("values" not in fields for _, _, fields in index.update_calls)
    assert len(conn.saved) == 1 and conn.saved[0][1]["chunks"][0]["categories"] == ["leave", "earned_leave"]

    index.update_calls.clear()
    conn.saved.clear()
    second = []
    backfill.execute(hr_args("--apply", "--namespace", "hr"), TAX, index, connect, second.append)
    text = "\n".join(second)
    assert index.update_calls == [] and conn.saved == []
    assert "to update    0" in text and text.count("to update    0") == 2        # Pinecone line and BM25 line


def test_a_failed_pinecone_write_is_returned_so_the_command_exits_non_zero():
    index = StrictIndex(make_index().store)
    index.fail_ids = {"hr-1"}
    connect, _ = make_connect({})
    assert backfill.execute(hr_args("--apply", "--namespace", "hr"), TAX, index, connect, lambda *_: None) == 1


# ---------------------------------------------------------------- report mode: stale keyword chunks and the reverse

def orphan_fixture():
    index = make_index()
    bm25 = [
        {"text": "Earned leave is 24 days", "source": "/tmp/handbook.pdf"},          # has a twin
        {"text": "stale text", "source": "/tmp/tmpxyz.pdf", "doc_id": "d9"},         # no twin, unknown document
        {"text": "stale but known", "source": "/tmp/handbook.pdf"},                  # no twin, known document
        "y",                                                                         # plain string; matches hr-3 by text
        "plain stale",                                                               # plain string, no match
    ]
    return index, bm25


def test_find_orphans_lists_both_directions_without_writing():
    index, bm25 = orphan_fixture()
    bm25_only, pinecone_only = backfill.find_orphans(backfill.all_chunks(index, "hr"), bm25, "hr", TAX)

    assert [o["position"] for o in bm25_only] == [1, 2, 4]
    assert bm25_only[0]["categories"] == ["uncategorized"] and bm25_only[0]["doc_id"] == "d9"
    assert bm25_only[1]["categories"] == ["leave", "earned_leave"]
    assert [o["chunk_id"] for o in pinecone_only] == ["hr-2"]          # hr-1 and hr-3 are in the keyword index
    assert index.update_calls == []


def test_a_namespace_in_sync_has_no_orphans():
    index = FakeIndex({"hr": {"a": {"source": "s", "text": "t1"}, "b": {"source": "s", "text": "t2"}}})
    assert backfill.find_orphans(backfill.all_chunks(index, "hr"),
                                 [{"text": "t1", "source": "s"}, {"text": "t2", "source": "s"}], "hr", TAX) == ([], [])


def test_report_orphans_through_execute_is_read_only_and_says_when_no_index_exists():
    index, bm25 = orphan_fixture()
    connect, conn = make_connect({"hr": pickle.dumps({"Bm25": "x", "chunks": bm25})})
    lines = []
    assert backfill.execute(hr_args("--report-orphans"), TAX, index, connect, lines.append) == 0

    text = "\n".join(lines)
    assert index.update_calls == [] and conn.saved == []
    assert "hr: 3 keyword-index chunks are not in Pinecone, 1 Pinecone chunks are not in the keyword index" in text
    assert "support: no keyword index stored" in text and "Nothing was changed" in text


def test_report_orphans_cannot_be_combined_with_apply():
    connect, _ = make_connect({})
    with pytest.raises(SystemExit):
        backfill.execute(hr_args("--report-orphans", "--apply"), TAX, make_index(), connect, lambda *_: None)
