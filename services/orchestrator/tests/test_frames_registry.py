"""Loading the hand-written frames and checking them against the taxonomy.

Run from services/orchestrator:  python -m pytest tests/test_frames_registry.py
Small made-up data for the rules; the real frames.yaml and the real taxonomy for the last section.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))
from shared.taxonomy.taxonomy import load_taxonomy, parse_taxonomy  # noqa: E402
from app.graph.frames.registry import build_registry, load_registry  # noqa: E402

TAX = parse_taxonomy({
    "hr": {
        "categories": {
            "leave": {"description": "All leave rules", "parents": []},
            "earned_leave": {"description": "Earned leave", "parents": ["leave"]},
            "payroll": {"description": "Salary payment", "parents": []},
        },
        "documents": {"handbook.pdf": ["leave", "earned_leave", "payroll"]},
    },
    "legal": {
        "categories": {"privacy": {"description": "Privacy law", "parents": []}},
        "documents": {"gdpr": ["privacy"]},
    },
})
GOOD = {
    "version": 2,
    "hr": {"hr.leave": {"description": "leave in general", "categories": ["leave"]},
           "hr.pay": {"description": "salary", "categories": ["payroll"]}},
    "legal": {"legal.privacy": {"description": "privacy law", "categories": ["privacy"]}},
}


# ---------------------------------------------------------------- building frames

def test_frames_are_grouped_by_domain_in_file_order():
    registry = build_registry(TAX, GOOD)
    assert [f.frame_id for f in registry["hr"]] == ["hr.leave", "hr.pay"]
    assert [f.frame_id for f in registry["legal"]] == ["legal.privacy"]


def test_a_frame_carries_its_domain_description_and_categories():
    frame = build_registry(TAX, GOOD)["hr"][0]
    assert (frame.domain, frame.description, frame.categories) == ("hr", "leave in general", ("leave",))


def test_a_domain_without_frames_is_simply_missing():
    assert "finance" not in build_registry(TAX, GOOD)


# ---------------------------------------------------------------- mistakes stop startup, with a clear message

@pytest.mark.parametrize("hand, message", [
    ({"hr.a": {"description": "d", "categories": ["nope"]}}, "hr.a: unknown category 'nope'"),
    ({"hr.a": {"description": "d", "categories": ["privacy"]}}, "hr.a: unknown category 'privacy'"),   # a legal category
    ({"legal.a": {"description": "d", "categories": ["leave"]}}, "the id must start with 'hr.'"),
    ({"hr.a": {"description": "  ", "categories": ["leave"]}}, "hr.a: needs a description"),
    ({"hr.a": {"categories": ["leave"]}}, "hr.a: needs a description"),
    ({"hr.a": {"description": "d", "categories": []}}, "hr.a: needs at least one category"),
    ({"hr.a": {"description": "d"}}, "hr.a: needs at least one category"),
    ({"hr.a": None}, "hr.a: needs a description"),
])
def test_a_bad_frame_is_refused_with_its_id(hand, message):
    with pytest.raises(ValueError, match="frames.yaml is invalid") as error:
        build_registry(TAX, {"hr": hand})
    assert message in str(error.value)


def test_an_unknown_domain_is_refused():
    with pytest.raises(ValueError, match="unknown domain 'sales'"):
        build_registry(TAX, {"sales": {"sales.a": {"description": "d", "categories": ["x"]}}})


def test_every_mistake_is_reported_together():
    bad = {"hr": {"hr.a": {"description": "d", "categories": ["nope"]}, "hr.b": {"categories": []}}}
    with pytest.raises(ValueError) as error:
        build_registry(TAX, bad)
    text = str(error.value)
    assert "hr.a: unknown category 'nope'" in text and "hr.b: needs a description" in text and "hr.b: needs at least one category" in text


# ---------------------------------------------------------------- the file

def test_the_frames_are_read_from_a_yaml_file(tmp_path):
    path = tmp_path / "frames.yaml"
    path.write_text("version: 2\nhr:\n  hr.leave:\n    description: leave in general\n    categories: [leave]\n", encoding="utf-8")
    assert [f.frame_id for f in load_registry(TAX, path=str(path))["hr"]] == ["hr.leave"]


# ---------------------------------------------------------------- the real frames.yaml against the real taxonomy

def test_the_real_frames_are_valid_and_every_domain_has_at_least_one():
    taxonomy = load_taxonomy()
    registry = load_registry(taxonomy)                      # raises if any frame names a category that does not exist
    assert set(registry) == {name for name in taxonomy.categories}
    assert 10 <= sum(len(frames) for frames in registry.values()) <= 12


def test_the_three_demo_frames_exist_and_name_what_the_demo_says():
    taxonomy = load_taxonomy()
    by_id = {f.frame_id: f for frames in load_registry(taxonomy).values() for f in frames}
    assert by_id["hr.leave_entitlement"].categories == ("earned_leave", "casual_and_sick_leave", "family_leave")
    assert by_id["hr.leave_overview"].categories == ("leave",)                    # a parent: the DAG walk adds its 4 children
    assert by_id["hr.provident_fund"].categories == ("provident_fund_and_gratuity",)   # two parents in the taxonomy
