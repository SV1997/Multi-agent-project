"""Tests for shared/taxonomy/chunk_labeler.py - one chunk's labels, chosen from its document's list.

Run from the repo root:  uv run python -m pytest shared/taxonomy/tests -q
The language model is a fake: it answers from a function, so no network is used and every case is exact.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from shared.taxonomy.chunk_labeler import ChunkLabels, build_prompt, label_chunks, only_candidates
from shared.taxonomy.tagging import tag_fields
from shared.taxonomy.taxonomy import parse_taxonomy

TAX = parse_taxonomy({
    "hr": {
        "categories": {
            "earned_leave": {"description": "Earned leave rules", "parents": []},
            "salary_payment": {"description": "When salary is paid", "parents": []},
            "medical_insurance": {"description": "Group medical insurance", "parents": []},
            "non_content": {"description": "Menus and link lists", "parents": []},
            "other_topic": {"description": "A topic this document does not cover", "parents": []},
        },
        "documents": {
            "handbook.pdf": ["earned_leave", "salary_payment", "medical_insurance"],
            "web_page.md": ["earned_leave", "non_content"],
            "one_topic.md": ["other_topic"],
        },
    }
})
HANDBOOK = list(TAX.for_chunk("hr", "handbook.pdf"))


class FakeModel:
    """Stands in for the language model: .batch() answers each chunk with answer_for(chunk_text)."""

    def __init__(self, answer_for):
        self.answer_for = answer_for
        self.calls = []

    def batch(self, messages, config=None, return_exceptions=False):
        self.calls.append(messages)
        return [self.answer_for(chunk[1][1]) for chunk in messages]      # chunk = [("system", ...), ("human", text)]


def labels(*names):
    return ChunkLabels(categories=list(names))


def test_the_models_choice_is_kept_in_the_documents_order_not_the_models():
    model = FakeModel(lambda text: labels("salary_payment", "earned_leave"))
    assert label_chunks(model, TAX, "hr", HANDBOOK, ["x"]) == [["earned_leave", "salary_payment"]]


def test_each_chunk_gets_its_own_labels():
    answers = {"leave text": labels("earned_leave"), "pay text": labels("salary_payment")}
    model = FakeModel(lambda text: answers[text])
    assert label_chunks(model, TAX, "hr", HANDBOOK, ["leave text", "pay text"]) == [["earned_leave"], ["salary_payment"]]


def test_a_category_the_document_does_not_list_is_thrown_away():
    model = FakeModel(lambda text: labels("earned_leave", "other_topic", "made_up"))
    assert label_chunks(model, TAX, "hr", HANDBOOK, ["x"]) == [["earned_leave"]]


def test_an_answer_with_nothing_valid_keeps_the_whole_document_list():
    model = FakeModel(lambda text: labels("made_up"))
    assert label_chunks(model, TAX, "hr", HANDBOOK, ["x"]) == [HANDBOOK]


def test_an_empty_answer_keeps_the_whole_document_list():
    model = FakeModel(lambda text: labels())
    assert label_chunks(model, TAX, "hr", HANDBOOK, ["x"]) == [HANDBOOK]


def test_one_failed_chunk_does_not_spoil_the_others():
    model = FakeModel(lambda text: RuntimeError("api down") if text == "bad" else labels("earned_leave"))
    assert label_chunks(model, TAX, "hr", HANDBOOK, ["good", "bad", "good"]) == [["earned_leave"], HANDBOOK, ["earned_leave"]]


def test_if_the_whole_call_fails_every_chunk_keeps_the_document_list():
    class Broken:
        def batch(self, *args, **kwargs):
            raise RuntimeError("no network")

    assert label_chunks(Broken(), TAX, "hr", HANDBOOK, ["a", "b"]) == [HANDBOOK, HANDBOOK]


def test_a_document_with_one_category_needs_no_model_call():
    model = FakeModel(lambda text: labels("other_topic"))
    assert label_chunks(model, TAX, "hr", ["other_topic"], ["a", "b"]) == [["other_topic"], ["other_topic"]]
    assert model.calls == []


def test_without_a_model_every_chunk_keeps_the_document_list():
    assert label_chunks(None, TAX, "hr", HANDBOOK, ["a", "b"]) == [HANDBOOK, HANDBOOK]


def test_the_prompt_describes_only_the_documents_categories():
    prompt = build_prompt(TAX, "hr", HANDBOOK)
    assert "Earned leave rules" in prompt and "When salary is paid" in prompt
    assert "A topic this document does not cover" not in prompt


def test_only_candidates_ignores_a_missing_answer():
    assert only_candidates(None, HANDBOOK) == []


# ---------- how a chunk's labels turn into the stored fields (tagging.py) ----------

def test_chunk_labels_replace_the_document_list_in_the_stored_fields():
    fields = tag_fields(TAX, "hr", "handbook.pdf", None, ["earned_leave"])
    assert fields["categories"] == ["earned_leave"]


def test_without_chunk_labels_the_stored_fields_are_exactly_as_before():
    assert tag_fields(TAX, "hr", "handbook.pdf")["categories"] == HANDBOOK


def test_a_menu_chunk_labelled_only_non_content_is_marked_not_content():
    model = FakeModel(lambda text: labels("non_content"))
    chosen = label_chunks(model, TAX, "hr", list(TAX.for_chunk("hr", "web_page.md")), ["Home | About | Contact"])[0]
    assert chosen == ["non_content"]
    assert tag_fields(TAX, "hr", "web_page.md", None, chosen)["is_content"] is False


def test_the_prompt_says_a_fragment_of_policy_text_is_not_non_content():
    prompt = build_prompt(TAX, "hr", list(TAX.for_chunk("hr", "web_page.md")))
    assert "NEVER non_content" in prompt and "list of citations" in prompt
