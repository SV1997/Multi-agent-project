"""Tests for shared/taxonomy/tagging.py - what a chunk should carry, and the smallest change to get there.

Run from the repo root:  uv run python -m pytest shared/taxonomy/tests -q
A tiny taxonomy is built in memory, so no file and no network is used.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from shared.taxonomy.taxonomy import parse_taxonomy
from shared.taxonomy.tagging import tag_fields, fields_to_set

DATA = {
    "hr": {
        "categories": {
            "leave": {"description": "All leave rules", "parents": []},
            "earned_leave": {"description": "Earned leave", "parents": ["leave"]},
            "non_content": {"description": "Menus and reference lists", "parents": []},
        },
        "documents": {
            "handbook.pdf": {"title": "HR Handbook", "categories": ["leave", "earned_leave"]},
            "menu.md": ["non_content"],
        },
    }
}
OVERRIDES = {
    "chunk-leave": {"domain": "hr", "categories": ["earned_leave"]},
    "chunk-menu": {"domain": "hr", "categories": ["non_content"]},
    "chunk-both": {"domain": "hr", "categories": ["non_content", "leave"]},
}
TAX = parse_taxonomy(DATA, OVERRIDES)


# ---------- tag_fields ----------

def test_a_chunk_override_wins_over_the_document_categories():
    fields = tag_fields(TAX, "hr", "/tmp/handbook.pdf", "chunk-leave")
    assert fields == {"categories": ["earned_leave"], "is_content": True, "title": "HR Handbook"}


def test_a_chunk_without_override_gets_its_documents_categories():
    fields = tag_fields(TAX, "hr", "/tmp/handbook.pdf", "some-other-chunk")
    assert fields["categories"] == ["leave", "earned_leave"]


def test_a_document_the_taxonomy_does_not_know_is_uncategorized_and_has_no_title():
    fields = tag_fields(TAX, "hr", "/tmp/new_file.pdf", "x")
    assert fields == {"categories": ["uncategorized"], "is_content": True}


def test_is_content_is_false_only_when_the_categories_are_exactly_non_content():
    assert tag_fields(TAX, "hr", "/tmp/menu.md", "x")["is_content"] is False        # document level
    assert tag_fields(TAX, "hr", "/tmp/handbook.pdf", "chunk-menu")["is_content"] is False   # chunk override
    assert tag_fields(TAX, "hr", "/tmp/handbook.pdf", "chunk-both")["is_content"] is True    # non_content plus a real category


def test_a_url_source_is_matched_by_its_last_path_segment():
    fields = tag_fields(TAX, "hr", "https://files.example.com/bucket/handbook.pdf?X-Amz-Signature=abc", "x")
    assert fields["categories"] == ["leave", "earned_leave"]


# ---------- fields_to_set ----------

def target_for_handbook():
    return tag_fields(TAX, "hr", "/tmp/handbook.pdf", "chunk-leave")


def test_nothing_to_write_when_the_chunk_is_already_correct():
    existing = {"categories": ["earned_leave"], "is_content": True, "title": "HR Handbook", "text": "..."}
    assert fields_to_set(target_for_handbook(), existing) == {}


def test_everything_is_written_for_a_chunk_with_no_tags():
    changes = fields_to_set(target_for_handbook(), {"text": "...", "source": "/tmp/handbook.pdf"})
    assert changes == {"categories": ["earned_leave"], "is_content": True, "title": "HR Handbook"}


def test_a_replaced_title_is_kept_once_as_original_title():
    existing = {"title": "Employee HR Policy Handbook - Short Demo Edition"}
    changes = fields_to_set(target_for_handbook(), existing)
    assert changes["title"] == "HR Handbook"
    assert changes["original_title"] == "Employee HR Policy Handbook - Short Demo Edition"


def test_an_existing_original_title_is_never_overwritten():
    existing = {"title": "Something else", "original_title": "The very first title"}
    changes = fields_to_set(target_for_handbook(), existing)
    assert "original_title" not in changes          # the first one stays
    assert changes["title"] == "HR Handbook"


def test_no_original_title_when_the_chunk_had_no_title_or_the_same_title():
    assert "original_title" not in fields_to_set(target_for_handbook(), {})
    same = {"title": "HR Handbook"}
    assert "title" not in fields_to_set(target_for_handbook(), same)


def test_a_taxonomy_without_a_title_leaves_the_stored_title_alone():
    target = tag_fields(TAX, "hr", "/tmp/menu.md", "x")            # menu.md has no title in the taxonomy
    changes = fields_to_set(target, {"title": "Page title from the HTML"})
    assert "title" not in changes and "original_title" not in changes


def test_writing_the_changes_makes_the_next_check_empty():
    existing = {"title": "Old title", "text": "..."}
    existing.update(fields_to_set(target_for_handbook(), existing))
    assert fields_to_set(target_for_handbook(), existing) == {}      # safe to run twice
    assert existing["original_title"] == "Old title"


# ---------- the uploaded file name ----------
# An uploaded file is stored under a signed url whose last part is "<uuid>-<name>", which never matches a yaml
# key. The name the user uploaded the file under (file_name) is what the yaml can be keyed on.

SIGNED_SOURCE = "https://files.example.com/bucket/0f8fad5b-d9cb-469f-a165-70867728950e-handbook.pdf?X-Amz-Signature=abc"


def test_the_uploaded_file_name_finds_the_document_when_the_stored_source_cannot():
    assert tag_fields(TAX, "hr", SIGNED_SOURCE, "x")["categories"] == ["uncategorized"]        # source alone: no match
    fields = tag_fields(TAX, "hr", SIGNED_SOURCE, "x", file_name="handbook.pdf")
    assert fields["categories"] == ["leave", "earned_leave"] and fields["title"] == "HR Handbook"


def test_the_file_name_is_preferred_over_the_source():
    # source says menu.md, the uploaded name says handbook.pdf: the uploaded name wins
    assert TAX.document_key("hr", "/tmp/menu.md", "x", file_name="handbook.pdf") == "handbook.pdf"


def test_a_file_name_the_taxonomy_does_not_know_falls_back_to_the_source():
    assert TAX.document_key("hr", "/tmp/handbook.pdf", "x", file_name="something_else.pdf") == "handbook.pdf"


def test_a_chunk_override_still_beats_the_file_name():
    fields = tag_fields(TAX, "hr", SIGNED_SOURCE, "chunk-leave", file_name="handbook.pdf")
    assert fields["categories"] == ["earned_leave"]


def test_calls_without_a_file_name_behave_exactly_as_before():
    assert TAX.for_chunk("hr", "/tmp/handbook.pdf", "x") == TAX.for_chunk("hr", "/tmp/handbook.pdf", "x", None)
    assert TAX.title_for("hr", "/tmp/handbook.pdf") == "HR Handbook"
