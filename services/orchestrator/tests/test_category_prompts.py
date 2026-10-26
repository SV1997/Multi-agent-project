"""Phase 6: category instructions, their validation, and the prompt block built from them.
Run from services/orchestrator:  python -m pytest tests/test_category_prompts.py

Small in-memory taxonomies for the rules; the last tests check the REAL category_prompts.yaml against the REAL
taxonomy and frames, including the rule that the instructions contain no numbers (so no policy facts).
"""
import os
import re
import sys

import pytest
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))
from shared.taxonomy.taxonomy import parse_taxonomy, load_taxonomy  # noqa: E402
from app.graph.frames.models import Frame  # noqa: E402
from app.graph.frames.prompts import (  # noqa: E402
    PromptError, parse_category_prompts, load_category_prompts, build_prompt_texts, choose_prompt_block,
    MAX_SCOPE, MAX_ITEM, HERE,
)
from app.graph.frames.registry import load_registry  # noqa: E402

TAX = parse_taxonomy({
    "hr": {
        "categories": {
            "leave": {"description": "All leave rules", "parents": []},
            "earned_leave": {"description": "Earned leave", "parents": ["leave"]},
            "sick_leave": {"description": "Sick leave", "parents": ["leave"]},
        },
        "documents": {"handbook.pdf": ["leave", "earned_leave", "sick_leave"]},
    },
    "legal": {
        "categories": {
            "privacy": {"description": "Privacy law", "parents": []},
            "non_content": {"description": "Menus", "parents": []},
        },
        "documents": {"gdpr": ["privacy"], "menu.md": ["non_content"]},
    },
})


def entry(scope="What it covers.", check=("Check this.",), ask=()):
    return {"scope": scope, "check": list(check), "ask": list(ask)}


GOOD = {
    "hr": {"leave": entry(), "earned_leave": entry("Earned leave only.", ("Confirm the type.", "Keep conditions with the entitlement."),
                                                    ("Which leave type?",)),
           "sick_leave": entry()},
    "legal": {"privacy": entry()},
}


# ---------------------------------------------------------------- validation

def test_valid_prompts_are_returned_per_domain_and_category():
    result = parse_category_prompts(TAX, GOOD)
    assert set(result) == {"hr", "legal"} and set(result["hr"]) == {"leave", "earned_leave", "sick_leave"}
    assert result["hr"]["earned_leave"] == {"scope": "Earned leave only.", "check": ["Confirm the type.", "Keep conditions with the entitlement."],
                                            "ask": ["Which leave type?"]}


def test_non_content_needs_no_prompt():
    assert "non_content" not in parse_category_prompts(TAX, GOOD)["legal"]


def mutate(**changes):
    data = {d: dict(c) for d, c in GOOD.items()}
    for path, value in changes.items():
        domain, category = path.split("__")
        data[domain][category] = value
    return data


@pytest.mark.parametrize("data, expected", [
    ({"hr": {"leave": entry()}, "legal": {"privacy": entry()}}, "hr: category 'earned_leave' has no prompt"),
    (mutate(), None),
    ({**GOOD, "hr": {**GOOD["hr"], "no_such_category": entry()}}, "hr: unknown category 'no_such_category'"),
    ({**GOOD, "legal": {**GOOD["legal"], "non_content": entry()}}, "never searched"),
    ({**GOOD, "sales": {}}, "unknown domain 'sales'"),
    (mutate(hr__leave=entry(scope="")), "hr.leave: needs a scope"),
    (mutate(hr__leave=entry(scope="x" * (MAX_SCOPE + 1))), "scope is"),
    (mutate(hr__leave=entry(check=())), "check needs 1 to 3 items"),
    (mutate(hr__leave=entry(check=("a", "b", "c", "d"))), "check needs 1 to 3 items"),
    (mutate(hr__leave=entry(ask=("a", "b", "c"))), "ask needs 0 to 2 items"),
    (mutate(hr__leave=entry(check=("y" * (MAX_ITEM + 1),))), "a check item is"),
    (mutate(hr__leave={"scope": "ok", "check": "not a list", "ask": []}), "check must be a list of non-empty strings"),
    (mutate(hr__leave=entry(check=("fine", ""))), "check must be a list of non-empty strings"),
    (mutate(hr__leave="just a string"), "must have scope, check and ask"),
])
def test_invalid_prompts_are_rejected_with_a_clear_message(data, expected):
    if expected is None:
        parse_category_prompts(TAX, data)                                  # the unchanged data is valid
        return
    with pytest.raises(PromptError) as error:
        parse_category_prompts(TAX, data)
    assert expected in str(error.value)


def test_all_problems_are_reported_together():
    bad = {"hr": {"leave": entry(scope=""), "ghost": entry()}, "legal": {}}
    with pytest.raises(PromptError) as error:
        parse_category_prompts(TAX, bad)
    message = str(error.value)
    for part in ("hr.leave: needs a scope", "unknown category 'ghost'", "'earned_leave' has no prompt", "legal: category 'privacy' has no prompt"):
        assert part in message


def test_a_missing_file_is_an_error_not_silence(tmp_path):
    with pytest.raises(PromptError, match="not found"):
        load_category_prompts(TAX, path=str(tmp_path / "nope.yaml"))


def test_prompts_are_read_from_the_given_file_or_the_environment(tmp_path, monkeypatch):
    path = tmp_path / "prompts.yaml"
    path.write_text(yaml.safe_dump(GOOD), encoding="utf-8")
    assert "earned_leave" in load_category_prompts(TAX, path=str(path))["hr"]
    monkeypatch.setenv("CATEGORY_PROMPTS_PATH", str(path))
    assert "privacy" in load_category_prompts(TAX)["legal"]


# ---------------------------------------------------------------- building the block

PROMPTS = parse_category_prompts(TAX, GOOD)
LEAVE_FRAME = Frame("hr.leave_entitlement", "hr", "d", ("earned_leave", "sick_leave"), {"leave_type": "Which leave?"}, (), "hand")


def texts(frame=LEAVE_FRAME, slots=None, missing=None, searched=None):
    return build_prompt_texts(frame, PROMPTS, slots or {}, missing or [], searched)


def test_the_block_names_the_frame_and_gives_each_categorys_instructions():
    base = texts()["base"]
    assert "frame hr.leave_entitlement" in base
    assert "- earned_leave: Earned leave only." in base and "- sick_leave: What it covers." in base
    assert "Check: Confirm the type." in base and "Check: Keep conditions with the entitlement." in base
    assert "What to find out from the user if it is not clear: Which leave type?" in base


def test_what_the_user_said_and_what_is_missing_are_listed():
    base = texts(slots={"leave_type": "earned leave"}, missing=["employment_status"])["base"]
    assert "What the user has told us: leave_type = earned leave" in base
    assert "Not yet known: employment_status" in base and "ask the user for it instead of guessing" in base
    plain = texts()["base"]
    assert "What the user has told us" not in plain and "Not yet known" not in plain


def test_only_the_strict_version_tells_the_agent_to_stay_inside_the_categories():
    result = texts(searched=["earned_leave", "sick_leave"])
    strict_rule = "Answer only from evidence in these categories: earned_leave, sick_leave. Do not borrow a rule from another category."
    assert strict_rule in result["strict"]
    assert "Do not borrow a rule from another category" not in result["base"]
    assert "Do not borrow a rule from another category" not in result["widened"]


def test_the_widened_version_allows_neighbouring_evidence_but_asks_for_care():
    widened = texts()["widened"]
    assert "was widened to related parts of the documents" in widened
    assert "say which part of the policy it comes from" in widened and "do not borrow a rule that belongs to a different situation" in widened
    assert "Answer only from evidence in these categories" not in widened          # it would contradict the evidence given


def test_the_strict_rule_defaults_to_the_frames_own_categories():
    assert "categories: earned_leave, sick_leave." in texts(searched=None)["strict"]


def test_the_other_frame_and_unknown_categories_give_no_block():
    other = Frame("hr.other", "hr", "d", (), {}, (), "other")
    assert build_prompt_texts(other, PROMPTS, {}, [], None) is None
    assert build_prompt_texts(Frame("hr.x", "hr", "d", ("not_in_prompts",), {}, (), "hand"), PROMPTS, {}, [], None) is None


def test_the_block_is_picked_by_where_the_evidence_came_from():
    state = {"category_prompts_text": texts()}
    assert choose_prompt_block({**state, "fallback_level": None}) == state["category_prompts_text"]["base"] + "\n\n"
    assert choose_prompt_block({**state, "fallback_level": 0}) == state["category_prompts_text"]["strict"] + "\n\n"
    assert choose_prompt_block({**state, "fallback_level": 1}) == state["category_prompts_text"]["widened"] + "\n\n"
    assert choose_prompt_block({**state, "fallback_level": 2}) == state["category_prompts_text"]["widened"] + "\n\n"


def test_no_block_when_there_are_no_prompt_texts():
    assert choose_prompt_block({}) == "" and choose_prompt_block({"category_prompts_text": None, "fallback_level": 0}) == ""


# ---------------------------------------------------------------- the real file

def real_instruction_texts(prompts):
    for domain, categories in prompts.items():
        for category, entry_ in categories.items():
            yield f"{domain}.{category}", [entry_["scope"], *entry_["check"], *entry_["ask"]]


def test_the_real_prompts_cover_every_searchable_category_of_the_real_taxonomy():
    taxonomy = load_taxonomy()
    prompts = load_category_prompts(taxonomy)
    for domain, categories in taxonomy.categories.items():
        assert set(prompts[domain]) == {c for c in categories if c != "non_content"}
    assert sum(len(v) for v in prompts.values()) == 45


def test_the_real_instructions_contain_no_numbers_and_so_no_policy_facts():
    """Instructions only. A digit, percent sign or currency sign would be a figure or a threshold; quote those from the documents."""
    prompts = load_category_prompts(load_taxonomy())
    offenders = [(where, text) for where, texts_ in real_instruction_texts(prompts) for text in texts_
                 if re.search(r"[0-9%$€£₹]", text)]
    assert offenders == []


def test_the_real_instructions_are_short_and_each_category_has_something_to_check():
    prompts = load_category_prompts(load_taxonomy())
    for where, texts_ in real_instruction_texts(prompts):
        assert all(len(t) <= MAX_SCOPE for t in texts_), where
    assert all(entry_["check"] for categories in prompts.values() for entry_ in categories.values())


def test_every_frame_in_the_real_menu_can_produce_a_prompt_block():
    taxonomy = load_taxonomy()
    prompts = load_category_prompts(taxonomy)
    registry = load_registry(taxonomy)
    for domain in taxonomy.categories:
        for frame in registry.menu(domain):
            built = build_prompt_texts(frame, prompts, {}, [], None)
            assert (built is None) == (frame.origin == "other"), frame.frame_id        # only "other" has no block


def test_the_prompts_file_is_next_to_frames_yaml():
    assert os.path.exists(os.path.join(HERE, "category_prompts.yaml")) and os.path.exists(os.path.join(HERE, "frames.yaml"))
