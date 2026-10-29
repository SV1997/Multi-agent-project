"""The frame step: pick a frame with one model call, expand its categories down the DAG, write the scope sentence.

Run from services/orchestrator:  python -m pytest tests/test_frame_node.py
The model is a fake that answers with a chosen number (or fails); the taxonomy and the frames are small and made up here.
"""
import logging
import os
import sys

import pytest
from langchain_core.messages import AIMessage, HumanMessage

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))
from shared.taxonomy.taxonomy import parse_taxonomy  # noqa: E402
from app.core import config  # noqa: E402
from app.graph.frames import node  # noqa: E402
from app.graph.frames.node import FrameChoice, debug_payload, frame_query_node  # noqa: E402
from app.graph.frames.prompts import scope_prompt  # noqa: E402
from app.graph.frames.registry import build_registry  # noqa: E402

TAX = parse_taxonomy({
    "hr": {
        "categories": {
            "leave": {"description": "All leave rules", "parents": []},
            "earned_leave": {"description": "Earned leave: accrual and encashment", "parents": ["leave"]},
            "sick_leave": {"description": "Sick leave and medical certificates", "parents": ["leave"]},
            "payroll": {"description": "Salary payment", "parents": []},
        },
        "documents": {"handbook.pdf": ["leave", "earned_leave", "sick_leave", "payroll"]},
    }
})
REGISTRY = build_registry(TAX, {"hr": {
    "hr.leave_entitlement": {"description": "how many days of a leave type an employee gets", "categories": ["earned_leave", "sick_leave"]},
    "hr.leave_overview": {"description": "leave in general", "categories": ["leave"]},
}})
FRAMES = REGISTRY["hr"]


def number_of(frame_id):
    return [frame.frame_id for frame in FRAMES].index(frame_id)


class FakeChooser:
    """Answers with the number it was given (or raises) and remembers what it was asked."""

    def __init__(self, number=None, error=None):
        self.number, self.error, self.asked = number, error, []

    def invoke(self, messages):
        self.asked.append(messages)
        if self.error:
            raise self.error
        return FrameChoice(number=self.number)


@pytest.fixture
def on(monkeypatch):
    """LOCALIZE on, the small taxonomy and frames, and a fake model: on(number) returns the fake model."""
    monkeypatch.setattr(config, "LOCALIZE", "on")
    monkeypatch.setattr(node, "load_taxonomy", lambda: TAX)
    monkeypatch.setattr(node, "load_registry", lambda taxonomy: REGISTRY)

    def use(number=None, error=None):
        chooser = FakeChooser(number, error)
        monkeypatch.setattr(node, "build_chooser", lambda: chooser)
        return chooser

    return use


def state(question="how many days of leave do I get?", **extra):
    return {"domain": "hr", "messages": [HumanMessage(content=question)], **extra}


# ---------------------------------------------------------------- switched off, or nothing to do

def test_with_localize_off_the_node_does_nothing_and_builds_no_model(monkeypatch):
    monkeypatch.setattr(config, "LOCALIZE", "off")
    monkeypatch.setattr(node, "build_chooser", lambda: pytest.fail("no model should be built while LOCALIZE is off"))
    assert frame_query_node(state()) == {}


def test_a_denied_user_gets_no_model_call(on):
    chooser = on(0)
    assert frame_query_node(state(authorization_denied=True)) == {} and chooser.asked == []


def test_no_user_message_means_no_frame_and_no_model_call(on):
    chooser = on(0)
    update = frame_query_node({"domain": "hr", "messages": [AIMessage(content="hello")]})
    assert update["localize_frame_id"] is None and update["localize_categories"] is None and chooser.asked == []


# ---------------------------------------------------------------- a frame is chosen

def test_a_chosen_frame_gives_its_categories_and_a_scope_sentence(on):
    on(number_of("hr.leave_entitlement"))
    update = frame_query_node(state())
    assert update["localize_frame_id"] == "hr.leave_entitlement"
    assert update["localize_categories"] == ["earned_leave", "sick_leave"]
    assert "how many days of a leave type an employee gets" in update["localize_scope"]
    assert update["localize_fallback_used"] is None


def test_a_frame_naming_a_parent_also_searches_its_children(on):
    on(number_of("hr.leave_overview"))
    assert frame_query_node(state("tell me about leave"))["localize_categories"] == ["leave", "earned_leave", "sick_leave"]


def test_the_model_sees_the_numbered_menu_and_only_the_latest_question(on):
    chooser = on(0)
    frame_query_node({"domain": "hr", "messages": [HumanMessage(content="old question"), AIMessage(content="an answer"),
                                                   HumanMessage(content="new question")]})
    system, human = chooser.asked[0]
    assert "0. hr.leave_entitlement: how many days" in system[1] and "answer -1" in system[1]
    assert human == ("human", "new question")


# ---------------------------------------------------------------- level 1: the parents' family, prepared for the retrieval service

def test_a_leaf_frame_prepares_the_parents_whole_family_as_level_one(on):
    on(number_of("hr.leave_entitlement"))
    update = frame_query_node(state())
    assert update["localize_categories"] == ["earned_leave", "sick_leave"]
    assert update["localize_wider_categories"] == ["leave", "earned_leave", "sick_leave"]
    assert update["localize_fallback_level"] is None


def test_a_frame_naming_the_top_parent_has_no_level_one(on):
    on(number_of("hr.leave_overview"))
    update = frame_query_node(state("tell me about leave"))
    assert update["localize_categories"] == ["leave", "earned_leave", "sick_leave"] and update["localize_wider_categories"] is None


@pytest.mark.parametrize("number", [-1, 99])
def test_no_frame_means_no_levels_at_all(on, number):
    on(number)
    update = frame_query_node(state())
    assert update["localize_categories"] is None and update["localize_wider_categories"] is None


# ---------------------------------------------------------------- no frame fits: no filter, never an error

@pytest.mark.parametrize("number", [-1, 99, 1000])
def test_a_number_off_the_menu_means_no_frame(on, number):
    on(number)
    update = frame_query_node(state())
    assert update["localize_frame_id"] is None and update["localize_categories"] is None and update["localize_scope"] is None


def test_a_failing_model_means_no_frame(on):
    on(error=RuntimeError("groq down"))
    update = frame_query_node(state())
    assert update["localize_frame_id"] is None and update["localize_categories"] is None


def test_every_run_clears_the_previous_turns_fallback_flag(on):
    on(error=RuntimeError("down"))
    assert frame_query_node(state(localize_fallback_used=True))["localize_fallback_used"] is None


def test_one_line_is_logged_with_the_question_frame_and_categories(on, caplog):
    on(number_of("hr.leave_entitlement"))
    with caplog.at_level(logging.INFO, logger="app.graph.frames.node"):
        frame_query_node(state("how many days?"))
    lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("frame ")]
    assert lines == ["frame hr.leave_entitlement | categories ['earned_leave', 'sick_leave'] | question 'how many days?'"]


def test_every_key_the_node_writes_is_a_field_of_the_graph_state(on):
    from app.graph.state import AgentState          # LangGraph refuses a node update that names an unknown field
    on(0)
    assert set(frame_query_node(state())) <= set(AgentState.__annotations__)


# ---------------------------------------------------------------- the scope prompt

def test_the_scope_prompt_names_the_frame_and_the_description_of_each_category():
    text = scope_prompt(TAX, FRAMES[number_of("hr.leave_entitlement")])
    assert text.startswith("This question is about how many days of a leave type an employee gets. The relevant policy areas are: ")
    assert "earned_leave: Earned leave: accrual and encashment; sick_leave: Sick leave and medical certificates" in text
    assert "Answer only from the provided context about these areas." in text and "say you do not know" in text


# ---------------------------------------------------------------- what the demo shows

def test_debug_information_shows_the_frame_the_levels_and_how_far_the_search_widened():
    values = {"localize_frame_id": "hr.leave_entitlement", "localize_categories": ["earned_leave"],
              "localize_wider_categories": ["leave", "earned_leave"], "localize_fallback_used": True, "localize_fallback_level": 1}
    assert debug_payload(values) == {"frame_id": "hr.leave_entitlement", "categories": ["earned_leave"],
                                     "wider_categories": ["leave", "earned_leave"], "fallback_used": True, "fallback_level": 1}


def test_there_is_no_debug_information_without_a_frame():
    assert debug_payload({}) is None and debug_payload({"localize_frame_id": None, "localize_categories": ["x"]}) is None
