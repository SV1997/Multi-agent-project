"""The menu the model chooses from, and reading its answer. Run from services/orchestrator: python -m pytest tests/test_frames_selection.py"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))
from app.graph.frames.models import Frame  # noqa: E402
from app.graph.frames.selection import frame_by_number, frames_by_numbers, menu_text  # noqa: E402

LEAVE = Frame("hr.leave_entitlement", "hr", "how many days of a leave type", ("earned_leave", "sick_leave"))
PAYROLL = Frame("hr.payroll", "hr", "salary payment", ("payroll",))
MENU = [LEAVE, PAYROLL]


def test_the_menu_is_numbered_from_zero_with_each_frames_description():
    assert menu_text(MENU).splitlines() == ["0. hr.leave_entitlement: how many days of a leave type",
                                            "1. hr.payroll: salary payment"]


def test_an_empty_menu_is_an_empty_text():
    assert menu_text([]) == ""


@pytest.mark.parametrize("number, expected_id", [
    (0, "hr.leave_entitlement"), (1, "hr.payroll"),
    (2, None), (-1, None), (99, None), (None, None), ("1", None), (1.0, None), (True, None),
])
def test_a_number_off_the_menu_selects_no_frame(number, expected_id):
    frame = frame_by_number(MENU, number)
    assert (frame.frame_id if frame else None) == expected_id


# ---------------------------------------------------------------- multi-frame selection (frames_by_numbers)

def test_two_valid_numbers_give_two_frames_in_order():
    assert [f.frame_id for f in frames_by_numbers(MENU, [1, 0])] == ["hr.payroll", "hr.leave_entitlement"]


def test_a_repeated_number_gives_that_frame_once():
    assert [f.frame_id for f in frames_by_numbers(MENU, [0, 0])] == ["hr.leave_entitlement"]


def test_a_bad_number_is_dropped_the_valid_ones_survive():
    assert [f.frame_id for f in frames_by_numbers(MENU, [99, 0, -1])] == ["hr.leave_entitlement"]


@pytest.mark.parametrize("numbers", [[], [99], [-1, 1000], None])
def test_no_valid_number_means_no_frame(numbers):
    assert frames_by_numbers(MENU, numbers) == []
