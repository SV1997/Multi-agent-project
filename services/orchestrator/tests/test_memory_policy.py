"""Long-term memory rules. Run from services/orchestrator: python -m pytest tests/test_memory_policy.py"""
import os
import sys
from datetime import datetime, timedelta
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.graph.memory_policy import (  # noqa: E402
    IDENTITY_ALIASES, build_memory_text, canonical_memory_key, is_negative_fact)

T0 = datetime(2026, 10, 18)


def item(key, content, days=0):
    return SimpleNamespace(key=key, value={"content": content}, updated_at=T0 + timedelta(days=days))


def test_identity_aliases_collapse_but_other_keys_do_not():
    assert canonical_memory_key("employee_name") == "name"
    assert canonical_memory_key("seat_location") == "location"
    assert canonical_memory_key("project_name") == "project_name"
    assert canonical_memory_key("contract_manager") == "contract_manager"


def test_negative_facts_detected_but_real_ones_kept():
    for bad in ("No name is on file for this employee.", "Location unknown", "Manager not available", "N/A"):
        assert is_negative_fact(bad), bad
    for good in ("Saharsh Vashishtha", "The employee is seated at desk B-19 in the Noida office.", "Full-Stack Developer"):
        assert not is_negative_fact(good), good


def test_identity_loaded_even_when_question_is_unrelated():
    items = {a: None for a in IDENTITY_ALIASES}
    items["name"] = item("name", "Saharsh Vashishtha")
    items["seat_location"] = item("seat_location", "The employee is seated at desk B-19 in the Noida office.")
    semantic = [item("leave_balance", "The employee has 5 casual leave days left.")]
    text = build_memory_text(items, semantic)
    assert "name: Saharsh Vashishtha" in text and "Noida office" in text and "casual leave" in text
    assert text.index("name:") < text.index("casual leave")  # identity first


def test_newest_alias_wins_and_false_fact_is_ignored():
    items = {a: None for a in IDENTITY_ALIASES}
    items["seat_location"] = item("seat_location", "desk B-19, Noida", days=0)
    items["workspace_location"] = item("workspace_location", "desk C-02, Pune", days=3)
    items["name"] = item("name", "No name is on file for this employee.", days=5)
    items["employee_name"] = item("employee_name", "Saharsh Vashishtha", days=1)
    text = build_memory_text(items, [])
    assert "location: desk C-02, Pune" in text and "B-19" not in text
    assert "name: Saharsh Vashishtha" in text and "No name" not in text


def test_semantic_duplicates_and_negatives_dropped_and_empty_is_none():
    items = {a: None for a in IDENTITY_ALIASES}
    items["name"] = item("name", "Saharsh Vashishtha")
    semantic = [item("employee_name", "Saharsh Vashishtha"), item("name_on_file", "No name is on file for this employee."),
                item("project", "The employee works on Project Orion.")]
    assert build_memory_text(items, semantic) == "name: Saharsh Vashishtha\nThe employee works on Project Orion."
    assert build_memory_text({a: None for a in IDENTITY_ALIASES}, []) is None
