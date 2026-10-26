"""Phase 5: widening a localized search along the taxonomy. Run from services/orchestrator:  python -m pytest tests/test_widen.py

Small in-memory taxonomies for the rules; the last tests walk the REAL taxonomy.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))
from shared.taxonomy.taxonomy import parse_taxonomy, load_taxonomy  # noqa: E402
from app.graph.frames.widen import descendants, expand_with_descendants, widen_levels  # noqa: E402

#   leave                 payroll            privacy (a root with no children)
#    |- earned_leave       |- tax_docs
#    |- sick_leave          |- salary_slips
#    |   |- sick_certificates
#    '- family_leave
TAX = parse_taxonomy({
    "hr": {
        "categories": {
            "leave": {"description": "All leave rules", "parents": []},
            "earned_leave": {"description": "Earned leave", "parents": ["leave"]},
            "sick_leave": {"description": "Sick leave", "parents": ["leave"]},
            "sick_certificates": {"description": "Medical certificates", "parents": ["sick_leave"]},
            "family_leave": {"description": "Family leave", "parents": ["leave"]},
            "payroll": {"description": "Salary", "parents": []},
            "tax_docs": {"description": "Tax documents", "parents": ["payroll"]},
            "salary_slips": {"description": "Salary slips", "parents": ["payroll"]},
            "privacy": {"description": "Privacy of staff data", "parents": []},
        },
        "documents": {"handbook.pdf": ["leave", "earned_leave", "sick_leave", "sick_certificates", "family_leave",
                                       "payroll", "tax_docs", "salary_slips", "privacy"]},
    }
})


def categories_of(levels, number):
    return levels[number]["categories"]


def test_descendants_cover_children_and_grandchildren_but_not_the_starting_category():
    assert descendants(TAX, "hr", ["leave"]) == {"earned_leave", "sick_leave", "sick_certificates", "family_leave"}
    assert descendants(TAX, "hr", ["sick_leave"]) == {"sick_certificates"}
    assert descendants(TAX, "hr", ["earned_leave"]) == set()
    assert descendants(TAX, "hr", ["earned_leave", "leave"]) == {"sick_leave", "sick_certificates", "family_leave"}


def test_a_listed_parent_is_expanded_to_its_descendants_and_the_given_order_is_kept():
    assert expand_with_descendants(TAX, "hr", ["earned_leave"]) == ["earned_leave"]               # a leaf stays as it is
    assert expand_with_descendants(TAX, "hr", ["payroll"]) == ["payroll", "tax_docs", "salary_slips"]
    assert expand_with_descendants(TAX, "hr", ["sick_leave", "earned_leave"]) == ["sick_leave", "earned_leave", "sick_certificates"]


def test_levels_for_a_leaf_category_go_to_its_parents_descendants_then_the_whole_domain():
    levels = widen_levels(TAX, "hr", ["earned_leave"])
    assert [l["level"] for l in levels] == [0, 1, 2]
    assert categories_of(levels, 0) == ["earned_leave"]
    assert categories_of(levels, 1) == ["leave", "earned_leave", "sick_leave", "sick_certificates", "family_leave"]
    assert categories_of(levels, 2) is None


def test_level_one_includes_the_parent_itself_because_some_chunks_are_labelled_with_it():
    assert "leave" in categories_of(widen_levels(TAX, "hr", ["earned_leave"]), 1)


def test_several_categories_widen_to_the_union_of_their_parents_families():
    levels = widen_levels(TAX, "hr", ["earned_leave", "tax_docs"])
    assert categories_of(levels, 0) == ["earned_leave", "tax_docs"]
    assert set(categories_of(levels, 1)) == {"leave", "earned_leave", "sick_leave", "sick_certificates", "family_leave",
                                              "payroll", "tax_docs", "salary_slips"}                    # both families, not privacy


def test_a_frame_naming_a_parent_is_searched_through_its_descendants_from_the_start():
    levels = widen_levels(TAX, "hr", ["sick_leave"])
    assert categories_of(levels, 0) == ["sick_leave", "sick_certificates"]
    assert categories_of(levels, 1) == ["leave", "earned_leave", "sick_leave", "sick_certificates", "family_leave"]


def test_a_category_with_no_parent_has_no_level_one_so_no_retry_is_wasted():
    levels = widen_levels(TAX, "hr", ["privacy"])
    assert levels == [{"level": 0, "categories": ["privacy"]}, {"level": 2, "categories": None}]    # 1 skipped, numbering kept


def test_a_root_whose_children_are_all_included_has_no_level_one_either():
    levels = widen_levels(TAX, "hr", ["payroll"])                                                    # payroll already covers tax_docs, salary_slips
    assert [l["level"] for l in levels] == [0, 2]


def test_the_other_frame_is_already_the_whole_domain_so_there_is_nothing_to_widen():
    assert widen_levels(TAX, "hr", []) == [{"level": 0, "categories": None}]
    assert widen_levels(TAX, "hr", None) == [{"level": 0, "categories": None}]


def test_each_level_is_at_least_as_wide_as_the_one_before_and_the_plan_is_plain_json():
    import json
    for start in (["earned_leave"], ["sick_certificates"], ["tax_docs", "family_leave"], ["leave"]):
        levels = widen_levels(TAX, "hr", start)
        sets = [set(l["categories"]) for l in levels if l["categories"] is not None]
        assert all(a < b for a, b in zip(sets, sets[1:]))                                            # strictly wider each step
        assert levels[-1]["categories"] is None and json.loads(json.dumps(levels)) == levels


def test_the_real_taxonomy_widens_sensibly_for_every_domain():
    taxonomy = load_taxonomy()
    for domain, categories in taxonomy.categories.items():
        for name in categories:
            levels = widen_levels(taxonomy, domain, [name])
            assert levels[0]["categories"][0] == name and levels[-1]["categories"] is None
            for level in levels:
                for category in level["categories"] or []:
                    assert category in categories                                                    # only real categories


def test_in_the_real_hr_taxonomy_earned_leave_widens_to_the_other_kinds_of_leave():
    taxonomy = load_taxonomy()
    level_one = widen_levels(taxonomy, "hr", ["earned_leave"])[1]["categories"]
    assert {"leave", "earned_leave", "casual_and_sick_leave", "family_leave", "comp_off_and_lwp"} <= set(level_one)
    assert "salary_payment" not in level_one                                                          # not a neighbour
