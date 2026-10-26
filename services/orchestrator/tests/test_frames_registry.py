"""Phase 4: building and validating the frames. Run from services/orchestrator:  python -m pytest tests/test_frames_registry.py

Small in-memory taxonomies are used for the rules; the last tests load the REAL taxonomy and the REAL frames.yaml,
so a typo in either shows up here.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))
from shared.taxonomy.taxonomy import parse_taxonomy, load_taxonomy  # noqa: E402
from app.graph.frames.registry import (  # noqa: E402
    FrameError, build_registry, load_registry, leaf_categories, auto_frames, other_frame,
)

DATA = {
    "hr": {
        "categories": {
            "leave": {"description": "All leave rules", "parents": []},
            "earned_leave": {"description": "Earned leave: accrual and carry forward", "parents": ["leave"]},
            "sick_leave": {"description": "Sick leave and certificates", "parents": ["leave"]},
            "payroll": {"description": "Salary payment", "parents": []},
            "non_content": {"description": "Menus and reference lists", "parents": []},
        },
        "documents": {
            "handbook.pdf": ["leave", "earned_leave", "sick_leave", "payroll"],
            "menu.md": ["non_content"],
        },
    },
    "legal": {
        "categories": {"privacy": {"description": "Privacy law", "parents": []}},
        "documents": {"gdpr": ["privacy"]},
    },
}
TAX = parse_taxonomy(DATA)


def hand(**frames):
    return {"hr": frames}


GOOD_HAND = hand(**{"hr.leave_entitlement": {
    "description": "How many days of a leave type",
    "categories": ["earned_leave", "sick_leave"],
    "required_slots": {"leave_type": "Which kind of leave?"},
    "optional_slots": ["employment_type"],
}})


# ---------------------------------------------------------------- generated frames

def test_a_frame_is_generated_for_each_leaf_category_but_not_for_parents_or_non_content():
    assert leaf_categories(TAX, "hr") == ["earned_leave", "sick_leave", "payroll"]      # leave has children; non_content skipped
    assert [f.frame_id for f in auto_frames(TAX, "hr")] == ["hr.earned_leave", "hr.sick_leave", "hr.payroll"]


def test_a_generated_frame_searches_its_category_and_uses_its_description():
    frame = auto_frames(TAX, "hr")[0]
    assert frame.categories == ("earned_leave",) and frame.description == "Earned leave: accrual and carry forward"
    assert frame.required_slots == {} and frame.origin == "auto"


def test_the_other_frame_searches_the_whole_domain():
    other = other_frame("hr")
    assert other.frame_id == "hr.other" and other.categories == () and other.origin == "other"


def test_the_menu_is_hand_written_then_generated_then_other():
    registry = build_registry(TAX, GOOD_HAND)
    assert [f.frame_id for f in registry.menu("hr")] == [
        "hr.leave_entitlement", "hr.earned_leave", "hr.sick_leave", "hr.payroll", "hr.other"]
    assert [f.frame_id for f in registry.menu("legal")] == ["legal.privacy", "legal.other"]
    assert registry.other("hr").frame_id == "hr.other"
    assert registry.get("hr", "hr.leave_entitlement").required_slots == {"leave_type": "Which kind of leave?"}
    assert registry.get("hr", "hr.nope") is None


def test_no_hand_written_frames_is_fine():
    assert [f.origin for f in build_registry(TAX, None).menu("legal")] == ["auto", "other"]


# ---------------------------------------------------------------- validation (every problem is reported at once)

@pytest.mark.parametrize("spec, expected_message", [
    ({"hr.a": {"description": "d", "categories": ["no_such_category"]}}, "unknown category 'no_such_category'"),
    ({"hr.a": {"description": "d", "categories": ["non_content"]}}, "cannot be searched by a frame"),
    ({"hr.a": {"description": "d", "categories": []}}, "needs at least one category"),
    ({"hr.a": {"description": "", "categories": ["payroll"]}}, "needs a description"),
    ({"hr.a": {"description": "d", "categories": ["payroll", "payroll"]}}, "a category is listed twice"),
    ({"legal.a": {"description": "d", "categories": ["payroll"]}}, "the id must start with 'hr.'"),
    ({"hr.other": {"description": "d", "categories": ["payroll"]}}, "reserved"),
    ({"hr.payroll": {"description": "d", "categories": ["payroll"]}}, "already generated for a category"),
    ({"hr.a": {"description": "d", "categories": ["payroll"], "required_slots": {"leave_type": ""}}}, "needs the question to ask"),
    ({"hr.a": {"description": "d", "categories": ["payroll"], "required_slots": {"Leave Type": "q?"}}}, "must be lowercase"),
    ({"hr.a": {"description": "d", "categories": ["payroll"], "required_slots": {"x": "q?"}, "optional_slots": ["x"]}}, "both required and optional"),
])
def test_invalid_hand_written_frames_are_rejected_with_a_clear_message(spec, expected_message):
    with pytest.raises(FrameError) as error:
        build_registry(TAX, {"hr": spec})
    assert expected_message in str(error.value)


def test_an_unknown_domain_is_rejected():
    with pytest.raises(FrameError, match="unknown domain 'sales'"):
        build_registry(TAX, {"sales": {"sales.a": {"description": "d", "categories": ["x"]}}})


def test_all_problems_are_reported_together():
    bad = hand(**{
        "hr.a": {"description": "", "categories": ["no_such_category"]},
        "hr.b": {"description": "d", "categories": []},
    })
    with pytest.raises(FrameError) as error:
        build_registry(TAX, bad)
    message = str(error.value)
    assert "needs a description" in message and "unknown category" in message and "needs at least one category" in message


# ---------------------------------------------------------------- the real files

def test_a_missing_frames_file_means_only_generated_frames(tmp_path):
    registry = load_registry(TAX, path=str(tmp_path / "does_not_exist.yaml"))
    assert [f.origin for f in registry.menu("hr")] == ["auto", "auto", "auto", "other"]


def test_the_real_frames_file_is_valid_against_the_real_taxonomy():
    taxonomy = load_taxonomy()
    registry = load_registry(taxonomy)

    hr_ids = [f.frame_id for f in registry.menu("hr")]
    assert hr_ids[:3] == ["hr.leave_entitlement", "hr.notice_period", "hr.leave_carry_forward"]   # the 3 examples first
    assert hr_ids[-1] == "hr.other"
    for domain in ("hr", "legal", "finance", "support", "engineering"):
        menu = registry.menu(domain)
        assert menu[-1].frame_id == f"{domain}.other"
        assert len({f.frame_id for f in menu}) == len(menu)                                        # no duplicate ids
        for frame in menu:
            for category in frame.categories:
                assert category in taxonomy.categories[domain]                                      # every category is real
    assert "non_content" not in {c for d in taxonomy.categories for f in registry.menu(d) for c in f.categories}


def test_every_leaf_category_of_the_real_taxonomy_can_be_reached_through_some_frame():
    taxonomy = load_taxonomy()
    registry = load_registry(taxonomy)
    for domain in taxonomy.categories:
        reachable = {c for f in registry.menu(domain) for c in f.categories}
        assert set(leaf_categories(taxonomy, domain)) <= reachable
