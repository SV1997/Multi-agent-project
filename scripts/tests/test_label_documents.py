"""Tests for scripts/label_documents.py with a fake Pinecone index: no network, no real taxonomy file.

Run from the repo root:  python -m pytest scripts/tests -q
"""
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import label_documents  # noqa: E402
from shared.taxonomy.taxonomy import parse_taxonomy  # noqa: E402

TAX = parse_taxonomy({
    "hr": {
        "categories": {
            "leave": {"description": "All leave rules", "parents": []},
            "earned_leave": {"description": "Earned leave", "parents": ["leave"]},
        },
        "documents": {"handbook.pdf": {"title": "HR Handbook", "categories": ["leave", "earned_leave"]}},
    },
    "legal": {
        "categories": {"privacy": {"description": "Privacy law", "parents": []}},
        "documents": {"gdpr": ["privacy"]},
    },
})
RIGHT = {"categories": ["leave", "earned_leave"], "is_content": True, "title": "HR Handbook"}


class FakeIndex:
    """Serverless-style index in memory. list() returns pages of 2 ids so paging is exercised too."""

    def __init__(self, store, fail_ids=()):
        self.store, self.fail_ids, self.updates = store, set(fail_ids), []

    def list(self, namespace):
        ids = list(self.store.get(namespace, {}))
        for start in range(0, len(ids), 2):
            yield ids[start:start + 2]

    def fetch(self, ids, namespace):
        found = {i: SimpleNamespace(metadata=dict(self.store[namespace][i])) for i in ids if i in self.store[namespace]}
        return SimpleNamespace(vectors=found)

    def update(self, id, set_metadata=None, namespace=None):
        if id in self.fail_ids:
            raise RuntimeError("pinecone said no")
        self.updates.append((namespace, id))
        self.store[namespace][id].update(set_metadata)

    def describe_index_stats(self):
        return SimpleNamespace(namespaces={ns: SimpleNamespace(vector_count=len(v)) for ns, v in self.store.items()})


def make_index(**kwargs):
    return FakeIndex({
        "hr": {
            "hr-1": {"source": "/tmp/handbook.pdf", "text": "Earned leave is 24 days", "title": "Old PDF title"},
            "hr-2": {"source": "/tmp/handbook.pdf", **RIGHT},                                  # already right
            "hr-3": {"source": "/tmp/brand_new.pdf", "text": "y"},                             # not in the yaml
            "hr-4": {"source": "http://x/0f8f-uuid-handbook.pdf?sig=1", "file_name": "handbook.pdf"},   # found by file name
        },
        "legal": {"legal-1": {"source": "https://x.org/gdpr?sig=1", "text": "Privacy rules"}},
        "coding": {"c-1": {"source": "/tmp/other.py", "text": "print(1)"}},
    }, **kwargs)


def lines_of(index, apply=False, only=None):
    lines = []
    failed = label_documents.run(index, TAX, only, apply, lines.append)
    return failed, "\n".join(lines)


def test_a_dry_run_counts_the_changes_per_domain_and_writes_nothing():
    index = make_index()
    failed, text = lines_of(index)
    assert failed == 0 and index.updates == []
    assert "DRY RUN" in text
    assert "hr           chunks     4 | to change     3" in text and "legal        chunks     1 | to change     1" in text


def test_apply_writes_the_missing_labels_and_nothing_else():
    index = make_index()
    lines_of(index, apply=True)
    assert index.store["hr"]["hr-1"]["categories"] == ["leave", "earned_leave"]
    assert index.store["hr"]["hr-1"]["text"] == "Earned leave is 24 days"          # other fields stay
    assert index.store["hr"]["hr-3"]["categories"] == ["uncategorized"]
    assert index.store["hr"]["hr-4"]["categories"] == ["leave", "earned_leave"]    # the file name found its document
    assert index.store["coding"]["c-1"] == {"source": "/tmp/other.py", "text": "print(1)"}


def test_the_old_title_is_kept_once_when_the_taxonomy_title_replaces_it():
    index = make_index()
    lines_of(index, apply=True)
    assert index.store["hr"]["hr-1"]["title"] == "HR Handbook" and index.store["hr"]["hr-1"]["original_title"] == "Old PDF title"


def test_a_second_apply_reports_zero_changes_and_writes_nothing():
    index = make_index()
    lines_of(index, apply=True)
    writes = len(index.updates)
    failed, text = lines_of(index, apply=True)
    assert failed == 0 and len(index.updates) == writes
    assert "to change     0" in text and "to change     3" not in text and "to change     1" not in text


def test_one_failing_chunk_does_not_stop_the_others_and_is_reported():
    index = make_index(fail_ids=["hr-1"])
    failed, text = lines_of(index, apply=True)
    assert failed == 1 and "FAILED [hr] hr-1" in text and "RuntimeError" in text
    assert "categories" in index.store["hr"]["hr-3"]


def test_a_namespace_that_is_not_in_the_taxonomy_is_skipped_with_a_warning():
    index = make_index()
    failed, text = lines_of(index, only="coding")
    assert failed == 0 and index.updates == [] and "'coding' is not in the taxonomy; skipped" in text


def test_index_namespaces_outside_the_taxonomy_are_warned_about_and_left_alone():
    _, text = lines_of(make_index())
    assert "namespace 'coding' in the index is not in the taxonomy; left alone" in text


def test_only_the_named_domain_is_labelled():
    index = make_index()
    lines_of(index, apply=True, only="legal")
    assert {namespace for namespace, _ in index.updates} == {"legal"}


# ---------------------------------------------------------------- chunk-level labels (--chunk-level)

class FakeLabeler:
    """Stands in for the model: .batch() answers each chunk by its text. Anything not listed gets an empty answer."""

    def __init__(self, answers):
        self.answers = answers

    def batch(self, messages, config=None, return_exceptions=False):
        from shared.taxonomy.chunk_labeler import ChunkLabels
        return [ChunkLabels(categories=self.answers.get(chunk[1][1], [])) for chunk in messages]


def chunk_level_run(index, apply=False, answers=None):
    lines = []
    labeler = FakeLabeler(answers if answers is not None else {"Earned leave is 24 days": ["earned_leave"]})
    failed = label_documents.run(index, TAX, "hr", apply, lines.append, labeler=labeler)
    return failed, "\n".join(lines)


def test_chunk_level_dry_run_shows_the_chosen_labels_and_writes_nothing():
    index = make_index()
    failed, text = chunk_level_run(index)
    assert failed == 0 and index.updates == []
    assert "categories per chunk:" in text and "e.g. ['earned_leave'] <- 'Earned leave is 24 days'" in text


def test_chunk_level_apply_gives_a_chunk_only_the_categories_the_model_chose():
    index = make_index()
    chunk_level_run(index, apply=True)
    assert index.store["hr"]["hr-1"]["categories"] == ["earned_leave"]                 # chosen, not the whole list
    assert index.store["hr"]["hr-3"]["categories"] == ["uncategorized"]                 # one candidate: no model needed


def test_a_chunk_without_text_keeps_its_documents_whole_list():
    index = make_index()
    chunk_level_run(index, apply=True)
    assert index.store["hr"]["hr-4"]["categories"] == ["leave", "earned_leave"]       # hr-4 has no stored text


def test_an_empty_model_answer_keeps_the_documents_whole_list():
    index = make_index()
    chunk_level_run(index, apply=True, answers={})
    assert index.store["hr"]["hr-1"]["categories"] == ["leave", "earned_leave"]


def test_a_second_chunk_level_apply_changes_nothing():
    index = make_index()
    chunk_level_run(index, apply=True)
    writes = len(index.updates)
    failed, text = chunk_level_run(index, apply=True)
    assert failed == 0 and len(index.updates) == writes and "to change     0" in text


# ---------------------------------------------------------------- keyword index (--keyword-index)

import contextlib  # noqa: E402
import pickle  # noqa: E402


class FakeCursor:
    def __init__(self, conn):
        self.conn, self.row = conn, None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=()):
        if sql.lstrip().startswith("SELECT"):
            self.row = self.conn.rows.get(params[0])
        else:                                                      # the UPDATE: (data, time, namespace)
            self.conn.rows[params[2]] = params[0]
            self.conn.writes += 1

    def fetchone(self):
        return (self.row,) if self.row is not None else None


class FakeConn:
    def __init__(self, rows):
        self.rows, self.writes = rows, 0

    def cursor(self):
        return FakeCursor(self)

    def transaction(self):
        return contextlib.nullcontext()


def keyword_conn():
    chunks = [
        {"text": "Earned leave is 24 days", "doc_id": "d1", "source": "handbook.pdf", "categories": ["leave", "earned_leave"], "is_content": True},
        {"text": "plain old chunk with no doc id", "doc_id": "zzz", "source": "x"},
    ]
    return FakeConn({"hr": pickle.dumps({"Bm25": "scorer", "chunks": chunks})})


LABELS = {("d1", "Earned leave is 24 days"): {"categories": ["earned_leave"], "is_content": True}}


def test_keyword_sync_dry_run_counts_the_changes_and_writes_nothing():
    conn = keyword_conn()
    result = label_documents.sync_keyword_index(conn, "hr", LABELS, apply=False)
    assert result == {"chunks": 2, "to_change": 1, "unmatched": 1} and conn.writes == 0


def test_keyword_sync_apply_rewrites_only_the_labels_of_matched_chunks():
    conn = keyword_conn()
    label_documents.sync_keyword_index(conn, "hr", LABELS, apply=True)
    data = pickle.loads(conn.rows["hr"])
    assert data["Bm25"] == "scorer"                                   # the scoring part is untouched
    assert data["chunks"][0]["categories"] == ["earned_leave"] and data["chunks"][0]["text"] == "Earned leave is 24 days"
    assert data["chunks"][1] == {"text": "plain old chunk with no doc id", "doc_id": "zzz", "source": "x"}   # unmatched: left alone


def test_keyword_sync_a_second_time_writes_nothing():
    conn = keyword_conn()
    label_documents.sync_keyword_index(conn, "hr", LABELS, apply=True)
    writes = conn.writes
    result = label_documents.sync_keyword_index(conn, "hr", LABELS, apply=True)
    assert result["to_change"] == 0 and conn.writes == writes


def test_a_namespace_with_no_keyword_index_is_skipped():
    assert label_documents.sync_keyword_index(FakeConn({}), "hr", LABELS, apply=True) == {"chunks": 0, "to_change": 0, "unmatched": 0}
