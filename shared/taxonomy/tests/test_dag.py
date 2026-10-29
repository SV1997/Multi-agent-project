"""The DAG walk: from a category down to everything beneath it, on the real policy_taxonomy.yaml.

Run from the repo root:  python -m pytest shared/taxonomy/tests -q
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from shared.taxonomy.taxonomy import descendants, expand_with_descendants, load_taxonomy, parents_family

TAX = load_taxonomy()
LEAVE_CHILDREN = ["earned_leave", "casual_and_sick_leave", "family_leave", "comp_off_and_lwp"]


def test_descendants_of_leave_are_its_four_children():
    assert descendants(TAX, "hr", ["leave"]) == set(LEAVE_CHILDREN)


def test_expanding_leave_gives_leave_first_then_its_four_children():
    assert expand_with_descendants(TAX, "hr", ["leave"]) == ["leave"] + LEAVE_CHILDREN


def test_a_leaf_has_no_descendants_and_expands_to_only_itself():
    assert descendants(TAX, "hr", ["earned_leave"]) == set()
    assert expand_with_descendants(TAX, "hr", ["earned_leave"]) == ["earned_leave"]


def test_provident_fund_has_two_parents_and_both_reach_it():
    # the reason this is a DAG and not a tree: a node may sit under more than one parent
    assert TAX.categories["hr"]["provident_fund_and_gratuity"].parents == ("payroll_and_tax", "benefits_and_expenses")
    assert "provident_fund_and_gratuity" in descendants(TAX, "hr", ["payroll_and_tax"])
    assert "provident_fund_and_gratuity" in descendants(TAX, "hr", ["benefits_and_expenses"])


def test_a_misspelt_category_is_dropped_instead_of_searched():
    assert expand_with_descendants(TAX, "hr", ["no_such_category"]) == []
    assert descendants(TAX, "hr", ["no_such_category"]) == set()


def test_naming_a_child_and_its_parent_gives_each_category_once():
    expanded = expand_with_descendants(TAX, "hr", ["earned_leave", "leave"])
    assert expanded[:2] == ["earned_leave", "leave"] and len(expanded) == len(set(expanded)) == 5


def test_a_domain_the_taxonomy_does_not_have_gives_nothing():
    assert expand_with_descendants(TAX, "sales", ["leave"]) == []


# ---------- the step upwards: the parents' whole family (level 1 of the widening)

def test_the_parents_family_of_a_leaf_is_its_parent_and_all_the_parents_children():
    assert parents_family(TAX, "hr", ["earned_leave"]) == ["leave"] + LEAVE_CHILDREN


def test_a_top_level_parent_has_no_wider_family_so_that_level_is_skipped():
    assert parents_family(TAX, "hr", ["leave"]) == []
    assert parents_family(TAX, "engineering", ["container_build_practices"]) == []


def test_provident_fund_widens_through_both_of_its_parents():
    family = parents_family(TAX, "hr", ["provident_fund_and_gratuity"])
    assert {"payroll_and_tax", "salary_payment", "benefits_and_expenses", "medical_insurance"} <= set(family)
    assert "leave" not in family                                    # unrelated branches stay out


def test_several_categories_share_one_family_without_repeats():
    family = parents_family(TAX, "hr", ["casual_and_sick_leave", "family_leave"])
    assert family == ["leave"] + LEAVE_CHILDREN and len(family) == len(set(family))


def test_a_misspelt_category_or_domain_has_no_wider_family():
    assert parents_family(TAX, "hr", ["no_such_category"]) == [] and parents_family(TAX, "sales", ["leave"]) == []
