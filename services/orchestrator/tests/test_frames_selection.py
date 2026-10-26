"""Phase 4: the plain rules around the model's choice of a frame. Run from services/orchestrator:  python -m pytest tests/test_frames_selection.py"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))
from app.graph.frames.models import Frame  # noqa: E402
from app.graph.frames.registry import other_frame  # noqa: E402
from app.graph.frames.selection import (  # noqa: E402
    words, number_words, menu_text, frame_by_number, ground_slots, missing_required, guard_rewrite,
)

LEAVE = Frame("hr.leave_entitlement", "hr", "How many days of a leave type", ("earned_leave", "sick_leave"),
              {"leave_type": "Which kind of leave?", "employment_status": "Confirmed or on probation?"}, ("grade",), "hand")
PAYROLL = Frame("hr.payroll", "hr", "Salary payment", ("payroll",), {}, (), "auto")
MENU = [LEAVE, PAYROLL, other_frame("hr")]


def test_words_ignore_case_and_punctuation():
    assert words("EMP-10492, B-14!") == {"emp", "10492", "b", "14"}
    assert number_words("Claim 12,500 for EMP-10492 on 3 March") == {"12", "500", "10492", "3"}


def test_the_menu_is_numbered_from_zero_and_lists_each_frames_slots():
    lines = menu_text(MENU).splitlines()
    assert lines[0] == ("0. hr.leave_entitlement: How many days of a leave type  "
                        "[slots: leave_type (required), employment_status (required), grade]")
    assert lines[1] == "1. hr.payroll: Salary payment"                  # no slots, no note
    assert lines[2].startswith("2. hr.other:")


@pytest.mark.parametrize("number, expected_id, valid", [
    (0, "hr.leave_entitlement", True), (1, "hr.payroll", True), (2, "hr.other", True),
    (3, "hr.other", False), (-1, "hr.other", False), (99, "hr.other", False),
    (None, "hr.other", False), ("1", "hr.other", False), (1.0, "hr.other", False), (True, "hr.other", False),
])
def test_a_number_off_the_menu_selects_other(number, expected_id, valid):
    frame, ok = frame_by_number(MENU, number)
    assert (frame.frame_id, ok) == (expected_id, valid)


# ---------------------------------------------------------------- slot grounding

def test_a_slot_value_is_kept_when_all_its_words_were_said():
    kept, dropped = ground_slots(LEAVE, [("leave_type", "Earned leave")], ["I want to know about earned leave, please"])
    assert kept == {"leave_type": "Earned leave"} and dropped == []


def test_a_value_the_user_never_said_is_dropped():
    kept, dropped = ground_slots(LEAVE, [("leave_type", "maternity")], ["how many days do I get?"])
    assert kept == {} and dropped == [("leave_type", "maternity", "not in the user's words or memories")]


def test_every_word_of_the_value_must_appear():
    kept, _ = ground_slots(LEAVE, [("leave_type", "maternity leave")], ["I am asking about maternity"])
    assert kept == {}                                                    # 'leave' was never said
    kept, _ = ground_slots(LEAVE, [("leave_type", "maternity leave")], ["I am asking about maternity", "leave for my wife"])
    assert kept == {"leave_type": "maternity leave"}                     # words may come from different sources


def test_a_slot_the_frame_does_not_have_is_dropped_even_if_it_was_said():
    kept, dropped = ground_slots(LEAVE, [("favourite_colour", "blue")], ["my favourite colour is blue"])
    assert kept == {} and dropped[0][2] == "not a slot of this frame"


def test_optional_slots_can_be_filled_and_the_first_value_wins():
    kept, _ = ground_slots(LEAVE, [("grade", "L4"), ("grade", "L5")], ["I am grade L4 and then L5"])
    assert kept == {"grade": "L4"}


def test_empty_values_and_no_sources_keep_nothing():
    assert ground_slots(LEAVE, [("leave_type", "  ")], ["anything"])[0] == {}
    assert ground_slots(LEAVE, [("leave_type", "earned")], [])[0] == {}


def test_missing_required_slots_are_listed_in_the_frames_order():
    assert missing_required(LEAVE, {}) == ["leave_type", "employment_status"]
    assert missing_required(LEAVE, {"leave_type": "earned"}) == ["employment_status"]
    assert missing_required(LEAVE, {"leave_type": "x", "employment_status": "y"}) == []
    assert missing_required(PAYROLL, {}) == []


# ---------------------------------------------------------------- the rewritten query

def test_a_good_rewrite_is_used():
    query, reason = guard_rewrite("How many earned leave days do I get?", "how many do I get?", ["earned leave"])
    assert (query, reason) == ("How many earned leave days do I get?", None)


def test_the_rewrite_may_use_a_number_that_was_said_anywhere_in_the_context():
    query, reason = guard_rewrite("status of claim 4471", "what about that claim?", ["I filed claim 4471 yesterday"])
    assert (query, reason) == ("status of claim 4471", None)


def test_a_rewrite_with_an_invented_number_falls_back_to_the_users_message():
    query, reason = guard_rewrite("How many of the 24 leave days are left?", "how many are left?", ["leave days"])
    assert query == "how many are left?" and reason == "contains a number that was never said"


@pytest.mark.parametrize("empty", ["", "   ", None])
def test_an_empty_rewrite_falls_back_to_the_users_message(empty):
    assert guard_rewrite(empty, "the message", []) == ("the message", "empty")


def test_a_rewrite_is_tidied():
    assert guard_rewrite("  leave   policy \n please ", "m", [])[0] == "leave policy please"
