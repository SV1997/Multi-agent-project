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
