"""Phase 4: the frame_query step, its routing, and the clarifying question.
Run from services/orchestrator:  python -m pytest tests/test_frame_node.py

The model is replaced by fakes that return a chosen FrameChoice (or fail), so the real checking code runs
against exactly the answers the test wants.
"""
import asyncio
import os
import sys

import pytest
from langchain_core.messages import AIMessage, HumanMessage

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))
from shared.taxonomy.taxonomy import parse_taxonomy  # noqa: E402
from app.graph.frames import node as frame_node  # noqa: E402
from app.graph.frames.node import (  # noqa: E402
    FrameChoice, SlotValue, NO_FRAME, FRAME_STATS, make_frame_query_node,
    route_after_authorization, route_after_frame, ask_for_slot,
)
from app.graph.frames.registry import build_registry  # noqa: E402

TAX = parse_taxonomy({
    "hr": {
        "categories": {
            "leave": {"description": "All leave rules", "parents": []},
            "earned_leave": {"description": "Earned leave", "parents": ["leave"]},
            "sick_leave": {"description": "Sick leave", "parents": ["leave"]},
            "payroll": {"description": "Salary payment", "parents": []},
        },
        "documents": {"handbook.pdf": ["leave", "earned_leave", "sick_leave", "payroll"]},
    }
})
REGISTRY = build_registry(TAX, {"hr": {
    "hr.leave_entitlement": {
        "description": "How many days of a leave type", "categories": ["earned_leave", "sick_leave"],
        "required_slots": {"leave_type": "Which kind of leave do you mean?"}, "optional_slots": ["employment_type"],
    },
    "hr.notice_period": {
        "description": "Notice period when resigning", "categories": ["payroll"],
        "required_slots": {"employment_status": "Are you confirmed, or still on probation?"},
    },
}})
# menu: 0 hr.leave_entitlement | 1 hr.notice_period | 2 hr.earned_leave | 3 hr.sick_leave | 4 hr.payroll | 5 hr.other


class FakeChooser:
    def __init__(self, result=None, error=None):
        self.result, self.error, self.calls = result, error, []

    async def ainvoke(self, messages):
        self.calls.append(messages)
        if self.error:
            raise self.error
        return self.result


def choice(number, slots=(), query="a standalone question"):
    return FrameChoice(number=number, slots=[SlotValue(name=n, value=v) for n, v in slots], standalone_query=query)


def run_node(chooser_results, state, level="filter"):
    """-> (state update, the choosers, so a test can read the prompts they were given)"""
    choosers = [(f"chooser {i}", c) for i, c in enumerate(chooser_results)]
    node = make_frame_query_node(REGISTRY, choosers, level=lambda: level)
    return asyncio.run(node(state)), chooser_results


def state_of(*messages, **extra):
    return {"domain": "hr", "messages": list(messages), **extra}


@pytest.fixture(autouse=True)
def fresh_counters():
    FRAME_STATS.clear()


# ---------------------------------------------------------------- switched off, or nothing to do

def test_with_localize_off_the_step_does_nothing_and_never_calls_the_model():
    chooser = FakeChooser(choice(0))
    update, _ = run_node([chooser], state_of(HumanMessage(content="how many days?")), level="off")
    assert update == NO_FRAME and chooser.calls == [] and dict(FRAME_STATS) == {}


def test_no_message_or_unknown_domain_means_no_frame_and_no_model_call():
    chooser = FakeChooser(choice(0))
    assert run_node([chooser], state_of())[0] == NO_FRAME
    assert run_node([chooser], {"domain": "sales", "messages": [HumanMessage(content="hi")]})[0] == NO_FRAME
    assert chooser.calls == []


def test_every_run_returns_all_the_frame_fields_so_nothing_leaks_between_turns():
    update, _ = run_node([FakeChooser(choice(2))], state_of(HumanMessage(content="earned leave rules")))
    assert set(update) == set(NO_FRAME)


# ---------------------------------------------------------------- a normal choice

def test_a_valid_choice_sets_the_frame_its_categories_and_the_grounded_slots():
    chooser = FakeChooser(choice(0, [("leave_type", "earned leave"), ("employment_type", "contract")],
                                 "How many days of earned leave do I get?"))
    update, _ = run_node([chooser], state_of(HumanMessage(content="how many earned leave days do I get?")))

    assert update["frame_id"] == "hr.leave_entitlement"
    assert update["localize_categories"] == ["earned_leave", "sick_leave"]
    assert update["frame_slots"] == {"leave_type": "earned leave"}          # "contract" was never said: dropped
    assert update["missing_slots"] == [] and update["clarifying_question"] is None
    assert update["rewritten_query"] == "How many days of earned leave do I get?"
    assert FRAME_STATS["calls"] == 1 and FRAME_STATS["ok"] == 1 and FRAME_STATS["slots_dropped"] == 1


def test_the_model_is_shown_the_menu_the_memories_and_the_latest_message():
    chooser = FakeChooser(choice(5))
    run_node([chooser], state_of(
        HumanMessage(content="what is the leave policy?"), AIMessage(content="It depends on the leave type."),
        HumanMessage(content="and for sick leave?"), conversation_memories="User is on probation"))

    system, user = chooser.calls[0]
    assert "0. hr.leave_entitlement: How many days of a leave type" in system.content and "5. hr.other" in system.content
    assert "Latest message: and for sick leave?" in user.content
    assert "User is on probation" in user.content
    assert "User: what is the leave policy?" in user.content and "Assistant: It depends on the leave type." in user.content


def test_a_frame_without_categories_leaves_the_search_unrestricted():
    update, _ = run_node([FakeChooser(choice(5))], state_of(HumanMessage(content="something odd")))
    assert update["frame_id"] == "hr.other" and update["localize_categories"] is None
    assert FRAME_STATS["invalid_choices"] == 0                     # choosing "other" on purpose is not an error


def test_a_rewrite_identical_to_the_message_is_not_stored():
    update, _ = run_node([FakeChooser(choice(2, query="earned leave rules"))], state_of(HumanMessage(content="earned leave rules")))
    assert update["rewritten_query"] is None


# ---------------------------------------------------------------- checking the model

def test_a_number_off_the_menu_becomes_other_and_is_counted():
    update, _ = run_node([FakeChooser(choice(99, [("leave_type", "earned")]))], state_of(HumanMessage(content="earned leave?")))
    assert update["frame_id"] == "hr.other" and update["localize_categories"] is None
    assert update["frame_slots"] == {}                              # "other" has no slots, so the proposed one is dropped
    assert FRAME_STATS["invalid_choices"] == 1 and FRAME_STATS["slots_dropped"] == 1


def test_a_rewrite_with_an_invented_number_is_refused_and_counted():
    update, _ = run_node([FakeChooser(choice(2, query="How many of the 24 earned leave days are left?"))],
                         state_of(HumanMessage(content="how many are left?")))
    assert update["rewritten_query"] is None and FRAME_STATS["rewrites_rejected"] == 1


def test_a_number_from_the_conversation_may_appear_in_the_rewrite():
    update, _ = run_node([FakeChooser(choice(2, query="earned leave days left out of 24")),],
                         state_of(HumanMessage(content="I have 24 days of earned leave"), AIMessage(content="ok"),
                                  HumanMessage(content="how many are left?")))
    assert update["rewritten_query"] == "earned leave days left out of 24"


def test_slot_values_are_grounded_in_stored_memories_too():
    update, _ = run_node([FakeChooser(choice(1, [("employment_status", "probation")]))],
                         state_of(HumanMessage(content="what is my notice period?"), conversation_memories="User is on probation"))
    assert update["frame_slots"] == {"employment_status": "probation"} and update["missing_slots"] == []


def test_the_assistants_own_words_do_not_ground_a_slot():
    messages = state_of(HumanMessage(content="how many leave days do I get?"),
                        AIMessage(content="Do you mean casual or earned leave?"),
                        HumanMessage(content="the first one"))
    update, _ = run_node([FakeChooser(choice(0, [("leave_type", "casual")]))], messages)
    assert update["frame_slots"] == {} and update["missing_slots"] == ["leave_type"]


# ---------------------------------------------------------------- model failures

def test_when_every_model_call_fails_there_is_no_frame():
    update, choosers = run_node([FakeChooser(error=RuntimeError("parse failed")), FakeChooser(error=RuntimeError("again"))],
                                state_of(HumanMessage(content="earned leave?")))
    assert update == NO_FRAME and all(len(c.calls) == 1 for c in choosers)
    assert FRAME_STATS["llm_failures"] == 1 and FRAME_STATS["ok"] == 0


def test_a_failing_first_method_falls_back_to_the_second():
    update, _ = run_node([FakeChooser(error=RuntimeError("parse failed")), FakeChooser(choice(2))],
                         state_of(HumanMessage(content="earned leave?")))
    assert update["frame_id"] == "hr.earned_leave" and FRAME_STATS["llm_failures"] == 0


# ---------------------------------------------------------------- asking for a missing slot

def test_a_missing_required_slot_is_asked_only_at_the_full_level():
    for level, asks in (("filter", False), ("prompt", False), ("full", True)):
        FRAME_STATS.clear()
        update, _ = run_node([FakeChooser(choice(0))], state_of(HumanMessage(content="how many days do I get?")), level=level)
        assert update["missing_slots"] == ["leave_type"]
        assert (update["clarifying_question"] == "Which kind of leave do you mean?") is asks
        assert FRAME_STATS["asked"] == (1 if asks else 0)


def test_after_the_user_answers_the_frame_is_chosen_again_and_nothing_is_missing():
    conversation = state_of(
        HumanMessage(content="how many leave days do I get?"),
        AIMessage(content="Which kind of leave do you mean?"),
        HumanMessage(content="earned leave"))
    update, chooser = run_node([FakeChooser(choice(0, [("leave_type", "earned leave")], "How many earned leave days do I get?"))],
                               conversation, level="full")
    assert update["missing_slots"] == [] and update["clarifying_question"] is None
    assert update["rewritten_query"] == "How many earned leave days do I get?"
    assert "User: how many leave days do I get?" in chooser[0].calls[0][1].content      # the earlier ask is in the context


# ---------------------------------------------------------------- routing and the question answer

def test_routing_after_authorization():
    assert route_after_authorization({"authorization_denied": True}) == "denied"
    assert route_after_authorization({"authorization_denied": False}) == "frame"
    assert route_after_authorization({}) == "frame"


def test_routing_after_the_frame_step():
    assert route_after_frame({"domain": "hr", "clarifying_question": "Which kind?"}) == "ask"
    assert route_after_frame({"domain": "hr", "clarifying_question": None}) == "hr"
    assert route_after_frame({"domain": "legal"}) == "legal"


def test_the_clarifying_question_becomes_the_answer_without_a_search():
    update = ask_for_slot({"domain": "hr", "clarifying_question": "Which kind of leave do you mean?"})
    assert update["messages"][0].content == "Which kind of leave do you mean?"
    final = update["final_answer"]
    assert final["answer"] == "Which kind of leave do you mean?" and final["sources"] == [] and final["context"] == []
    assert final["confidence"] == 1.0 and final["requires_human_review"] is False and update["requires_human_review"] is False


# ---------------------------------------------------------------- inside a real LangGraph graph (with a checkpointer)

def mini_graph(chooser, level, seen):
    """frame_query -> (ask_for_slot | a fake hr_agent), built with the real node, the real routing and the real AgentState."""
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.graph import StateGraph, END
    from app.graph.state import AgentState

    def hr_agent(state):
        seen.append({key: state.get(key) for key in ("frame_id", "frame_slots", "localize_categories", "rewritten_query")})
        return {"messages": [AIMessage(content="the answer")], "final_answer": {"answer": "the answer"}}

    node = make_frame_query_node(REGISTRY, [("c", chooser)], level=lambda: level)
    graph = StateGraph(AgentState)
    graph.add_node("frame_query", node)
    graph.add_node("ask_for_slot", ask_for_slot)
    graph.add_node("hr_agent", hr_agent)
    graph.set_entry_point("frame_query")
    graph.add_conditional_edges("frame_query", route_after_frame, {"hr": "hr_agent", "ask": "ask_for_slot"})
    graph.add_edge("hr_agent", END)
    graph.add_edge("ask_for_slot", END)
    return graph.compile(checkpointer=MemorySaver())


def ask(app, text, thread="t1"):
    return asyncio.run(app.ainvoke({"domain": "hr", "messages": [HumanMessage(content=text)]},
                                   config={"configurable": {"thread_id": thread}}))


def test_a_missing_slot_ends_the_run_with_the_question_and_never_reaches_the_agent():
    seen = []
    result = ask(mini_graph(FakeChooser(choice(0)), "full", seen), "how many days do I get?")

    assert seen == []                                                           # the agent did not run
    assert result["messages"][-1].content == "Which kind of leave do you mean?"
    assert result["final_answer"]["answer"] == "Which kind of leave do you mean?"
    assert result["frame_id"] == "hr.leave_entitlement" and result["missing_slots"] == ["leave_type"]


def test_the_agent_starts_with_the_frames_categories_and_the_standalone_question_in_the_state():
    seen = []
    ask(mini_graph(FakeChooser(choice(0, [("leave_type", "earned leave")], "How many earned leave days do I get?")), "full", seen),
        "how many earned leave days do I get?... or rather, how many do I get for earned leave")
    assert seen == [{"frame_id": "hr.leave_entitlement", "frame_slots": {"leave_type": "earned leave"},
                     "localize_categories": ["earned_leave", "sick_leave"], "rewritten_query": "How many earned leave days do I get?"}]


def test_a_frame_never_leaks_into_the_next_turn_of_the_same_thread():
    seen = []
    chooser = FakeChooser(choice(2, query="rewritten for turn one"))
    app = mini_graph(chooser, "filter", seen)
    ask(app, "earned leave rules", thread="same")
    assert seen[0]["frame_id"] == "hr.earned_leave" and seen[0]["rewritten_query"] == "rewritten for turn one"

    chooser.result, chooser.error = None, RuntimeError("model down")             # the next turn: the model fails
    ask(app, "something else entirely", thread="same")
    assert seen[1] == {"frame_id": None, "frame_slots": None, "localize_categories": None, "rewritten_query": None}


def test_with_localize_off_the_graph_goes_straight_to_the_agent_with_no_frame_in_the_state():
    seen = []
    chooser = FakeChooser(choice(0))
    ask(mini_graph(chooser, "off", seen), "how many days do I get?")
    assert seen == [{"frame_id": None, "frame_slots": None, "localize_categories": None, "rewritten_query": None}]
    assert chooser.calls == []


def test_a_stale_dag_from_the_previous_turn_is_cleared_even_when_this_turn_ends_with_a_question():
    app = mini_graph(FakeChooser(choice(0)), "full", [])
    result = asyncio.run(app.ainvoke(
        {"domain": "hr", "messages": [HumanMessage(content="how many days do I get?")], "query_dag": {"stale": "from the last turn"}},
        config={"configurable": {"thread_id": "stale"}}))
    assert result["clarifying_question"] and result["query_dag"] is None


# ---------------------------------------------------------------- staying with the frame that asked

def test_the_asked_frame_is_remembered_only_when_a_question_is_asked():
    asking, _ = run_node([FakeChooser(choice(0))], state_of(HumanMessage(content="how many days?")), level="full")
    assert asking["asked_frame_id"] == "hr.leave_entitlement"
    not_asking, _ = run_node([FakeChooser(choice(0))], state_of(HumanMessage(content="how many days?")), level="filter")
    assert not_asking["asked_frame_id"] is None                       # nothing was asked at the filter level
    complete, _ = run_node([FakeChooser(choice(0, [("leave_type", "earned")]))], state_of(HumanMessage(content="earned leave days?")), level="full")
    assert complete["asked_frame_id"] is None


def test_the_model_is_reminded_which_frame_asked_the_previous_question():
    chooser = FakeChooser(choice(1, [("employment_status", "probation")]))
    run_node([chooser], state_of(HumanMessage(content="what is my notice period?"), AIMessage(content="Are you confirmed, or still on probation?"),
                                 HumanMessage(content="I am still on probation"), asked_frame_id="hr.notice_period"), level="full")
    prompt = chooser.calls[0][1].content
    assert "frame hr.notice_period" in prompt and "choose that same frame" in prompt
    assert prompt.index("choose that same frame") < prompt.index("Latest message:")


@pytest.mark.parametrize("asked", [None, "", "hr.not_a_frame_on_this_menu", "legal.privacy"])
def test_no_reminder_without_a_valid_asked_frame(asked):
    chooser = FakeChooser(choice(5))
    run_node([chooser], state_of(HumanMessage(content="hello"), asked_frame_id=asked))
    assert "choose that same frame" not in chooser.calls[0][1].content


class SequenceChooser:
    """Returns the next prepared choice on each call and keeps every prompt it was given."""
    def __init__(self, *results):
        self.results, self.calls = list(results), []

    async def ainvoke(self, messages):
        self.calls.append(messages)
        return self.results.pop(0)


def test_a_two_turn_conversation_asks_then_stays_with_the_same_frame():
    seen = []
    chooser = SequenceChooser(choice(1), choice(1, [("employment_status", "probation")], "What is the notice period for someone on probation?"))
    app = mini_graph(chooser, "full", seen)

    first = ask(app, "what is my notice period?", thread="two-turns")
    assert first["asked_frame_id"] == "hr.notice_period" and first["clarifying_question"] == "Are you confirmed, or still on probation?"
    assert seen == []                                                          # no agent yet

    second = asyncio.run(app.ainvoke({"messages": [HumanMessage(content="I am still on probation")]},
                                     config={"configurable": {"thread_id": "two-turns"}}))
    assert "frame hr.notice_period" in chooser.calls[1][1].content            # the reminder reached the model
    assert second["asked_frame_id"] is None                                    # answered: forgotten again
    assert seen == [{"frame_id": "hr.notice_period", "frame_slots": {"employment_status": "probation"},
                     "localize_categories": ["payroll"], "rewritten_query": "What is the notice period for someone on probation?"}]


# ---------------------------------------------------------------- the search plan (widening)

def run_with_taxonomy(chooser, state, level="filter"):
    node = make_frame_query_node(REGISTRY, [("c", chooser)], level=lambda: level, taxonomy=TAX)
    return asyncio.run(node(state))


def test_with_a_taxonomy_the_node_leaves_a_search_plan_that_widens_to_the_parents_family():
    update = run_with_taxonomy(FakeChooser(choice(2)), state_of(HumanMessage(content="earned leave rules")))     # hr.earned_leave
    assert [l["level"] for l in update["localize_levels"]] == [0, 1, 2]
    assert update["localize_levels"][0]["categories"] == ["earned_leave"] == update["localize_categories"]
    assert update["localize_levels"][1]["categories"] == ["leave", "earned_leave", "sick_leave"]
    assert update["localize_levels"][2]["categories"] is None


def test_a_hand_written_frame_widens_from_all_its_categories():
    update = run_with_taxonomy(FakeChooser(choice(0)), state_of(HumanMessage(content="how many days do I get?")))   # leave_entitlement
    assert update["localize_levels"][0]["categories"] == ["earned_leave", "sick_leave"]
    assert update["localize_levels"][1]["categories"] == ["leave", "earned_leave", "sick_leave"]


def test_the_other_frame_has_a_single_level_that_is_the_whole_domain():
    update = run_with_taxonomy(FakeChooser(choice(5)), state_of(HumanMessage(content="something odd")))
    assert update["localize_levels"] == [{"level": 0, "categories": None}] and update["localize_categories"] is None


def test_without_a_taxonomy_there_is_no_plan_and_the_frames_own_categories_are_used():
    update, _ = run_node([FakeChooser(choice(2))], state_of(HumanMessage(content="earned leave rules")))
    assert update["localize_levels"] is None and update["localize_categories"] == ["earned_leave"]


def test_the_plan_and_the_retrieval_trace_are_cleared_when_there_is_no_frame():
    off, _ = run_node([FakeChooser(choice(2))], state_of(HumanMessage(content="x")), level="off")
    failed, _ = run_node([FakeChooser(error=RuntimeError("down"))], state_of(HumanMessage(content="x")))
    for update in (off, failed):
        assert update["localize_levels"] is None and update["fallback_level"] is None and update["levels_tried"] is None


def test_a_new_turn_clears_the_previous_turns_trace_even_when_it_ends_with_a_question():
    app = mini_graph(FakeChooser(choice(0)), "full", [])
    result = asyncio.run(app.ainvoke(
        {"domain": "hr", "messages": [HumanMessage(content="how many days do I get?")],
         "fallback_level": 2, "levels_tried": [0, 1, 2], "localize_levels": [{"level": 0, "categories": ["old"]}]},
        config={"configurable": {"thread_id": "old-trace"}}))
    assert result["clarifying_question"] and result["fallback_level"] is None and result["levels_tried"] is None


# ---------------------------------------------------------------- the category instructions for the answering prompt

from app.graph.frames.prompts import parse_category_prompts  # noqa: E402

PROMPTS = parse_category_prompts(TAX, {"hr": {
    name: {"scope": f"Scope of {name}.", "check": [f"Check for {name}."], "ask": []}
    for name in ("leave", "earned_leave", "sick_leave", "payroll")}})


def run_with_prompts(chooser, state, level, prompts=PROMPTS):
    node = make_frame_query_node(REGISTRY, [("c", chooser)], level=lambda: level, taxonomy=TAX, prompts=prompts)
    return asyncio.run(node(state))


@pytest.mark.parametrize("level, expects_block", [("off", False), ("filter", False), ("prompt", True), ("full", True)])
def test_the_prompt_block_is_built_only_at_the_prompt_and_full_levels(level, expects_block):
    update = run_with_prompts(FakeChooser(choice(2)), state_of(HumanMessage(content="earned leave rules")), level)   # hr.earned_leave
    assert (update["category_prompts_text"] is not None) is expects_block


def test_the_block_names_the_frame_the_slots_and_what_is_missing():
    update = run_with_prompts(FakeChooser(choice(0, [("leave_type", "earned leave")])),
                              state_of(HumanMessage(content="how many earned leave days do I get?")), "prompt")
    base = update["category_prompts_text"]["base"]
    assert "frame hr.leave_entitlement" in base and "- earned_leave: Scope of earned_leave." in base and "- sick_leave:" in base
    assert "leave_type = earned leave" in base and "Not yet known" not in base

    missing = run_with_prompts(FakeChooser(choice(0)), state_of(HumanMessage(content="how many days do I get?")), "prompt")
    assert "Not yet known: leave_type" in missing["category_prompts_text"]["base"]


def test_the_strict_rule_names_the_categories_the_first_search_covers():
    update = run_with_prompts(FakeChooser(choice(0)), state_of(HumanMessage(content="days?")), "prompt")
    assert "Answer only from evidence in these categories: earned_leave, sick_leave." in update["category_prompts_text"]["strict"]


def test_no_block_for_the_other_frame_or_without_prompts():
    other = run_with_prompts(FakeChooser(choice(5)), state_of(HumanMessage(content="odd")), "prompt")
    assert other["category_prompts_text"] is None
    without = run_with_prompts(FakeChooser(choice(2)), state_of(HumanMessage(content="earned leave rules")), "prompt", prompts=None)
    assert without["category_prompts_text"] is None


def test_the_block_is_cleared_when_there_is_no_frame():
    failed = run_with_prompts(FakeChooser(error=RuntimeError("down")), state_of(HumanMessage(content="x")), "prompt")
    assert failed["category_prompts_text"] is None
    off, _ = run_node([FakeChooser(choice(2))], state_of(HumanMessage(content="x")), level="off")
    assert off["category_prompts_text"] is None
