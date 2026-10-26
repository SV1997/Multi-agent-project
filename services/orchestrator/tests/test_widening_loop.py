"""Phase 5: a localized search widens when it finds nothing, inside the REAL domain-agent graph.
Run from services/orchestrator:  python -m pytest tests/test_widening_loop.py

What is real: build_domain_agent (planner -> search -> grade -> rewrite -> search ... -> answer), the real
retrieve_context, the real retry rules, the real widening plan from a taxonomy.
What is fake: the language model (it plans "vector", grades a search relevant only if passages came back, and
answers) and the retrieval service (a small labelled corpus, filtered by the categories in the request exactly
as the real service filters).
"""
import asyncio
import os
import sys

import pytest
from langchain_core.messages import AIMessage, HumanMessage

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))
from shared.contracts.schema import AgentAnswerLLM, RetrievalAssessment, RetrievalPlan, RewrittenQuery  # noqa: E402
from shared.taxonomy.taxonomy import parse_taxonomy  # noqa: E402
from app.graph.agents.base import nodes  # noqa: E402
from app.graph.agents.base.agent_factory import build_domain_agent  # noqa: E402
from app.graph.frames.widen import widen_levels  # noqa: E402

TAX = parse_taxonomy({
    "hr": {
        "categories": {
            "leave": {"description": "All leave rules", "parents": []},
            "earned_leave": {"description": "Earned leave", "parents": ["leave"]},
            "sick_leave": {"description": "Sick leave", "parents": ["leave"]},
            "payroll": {"description": "Salary", "parents": []},
            "privacy": {"description": "Privacy of staff data", "parents": []},
        },
        "documents": {"handbook.pdf": ["leave", "earned_leave", "sick_leave", "payroll", "privacy"]},
    }
})


class FakeStructured:
    def __init__(self, llm, schema):
        self.llm, self.schema = llm, schema

    def with_config(self, *args, **kwargs):
        return self

    def with_retry(self, *args, **kwargs):
        return self

    async def ainvoke(self, messages):
        name = self.schema.__name__
        self.llm.calls.append(name)
        if name == "RetrievalPlan":
            return RetrievalPlan(needs_retrieval=True, source="vector", reason="a policy question")
        if name == "RetrievalAssessment":
            found = "No passages were returned." not in messages[-1].content
            return RetrievalAssessment(relevant=found, reason="passages found" if found else "nothing found", can_be_answered_by_tool=False)
        if name == "RewrittenQuery":
            return RewrittenQuery(search_query=f"rewritten query {self.llm.calls.count('RewrittenQuery')}")
        if name == "AgentAnswerLLM":
            return AgentAnswerLLM(confidence=0.9, requires_human_review=False, conflict_detected=False)
        raise AssertionError(f"unexpected structured output {name}")


class FakeLLM:
    def __init__(self):
        self.calls = []
        self.answer_prompts = []          # the messages the answering call received

    def model_copy(self, update=None):
        return self

    def with_config(self, *args, **kwargs):
        return self

    def bind_tools(self, tools):
        return self

    def with_structured_output(self, schema, **kwargs):
        return FakeStructured(self, schema)

    async def ainvoke(self, messages):
        self.calls.append("answer")
        self.answer_prompts.append(messages)
        return AIMessage(content="The answer, written from the evidence.")


class FakeRetrievalService:
    """Filters CORPUS by the categories in each request, like the real service does with LOCALIZE on."""
    corpus: list = []
    requests: list = []

    def __init__(self, **_):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def post(self, url, json, headers):
        FakeRetrievalService.requests.append(json)
        wanted = set(json.get("categories") or [])
        hits = [c for c in FakeRetrievalService.corpus if not wanted or wanted & set(c["metadata"]["categories"])]
        body = {"results": hits}
        return type("Response", (), {"raise_for_status": lambda self: None, "json": lambda self: body})()


def chunk(text, *categories):
    return {"source": "handbook.pdf", "content": text, "score": 0.5, "metadata": {"categories": list(categories), "is_content": True}}


@pytest.fixture
def run_agent(monkeypatch):
    """run_agent(corpus, frame_categories=[...] | None, localize=True) -> (final state, the llm, the retrieval requests)"""
    monkeypatch.setattr(nodes.httpx, "AsyncClient", FakeRetrievalService)

    def run(corpus, frame_categories, localize=True, extra=None):
        FakeRetrievalService.corpus, FakeRetrievalService.requests = corpus, []
        llm = FakeLLM()
        agent = build_domain_agent(llm, "You are the HR agent.", tools=[], domain_name="hr", retrieval_method=["vector"])
        state = {
            "domain": "hr", "messages": [HumanMessage(content="how many earned leave days do I get?")],
            "retrieved_context": [], "react_trace": [], "tool_calls_remaining": 6, "requires_human_review": False,
            "final_answer": None, "allowed_namespace": ["hr"], "employee_email": "a@b.c",
        }
        if localize:
            levels = widen_levels(TAX, "hr", frame_categories)
            state.update(localize_levels=levels, localize_categories=levels[0]["categories"], frame_id="hr.x")
        state.update(extra or {})
        final = asyncio.run(agent.ainvoke(state))
        return final, llm, FakeRetrievalService.requests

    return run


def categories_asked(requests):
    return [r.get("categories") for r in requests]


# ---------------------------------------------------------------- widening, level by level

def test_evidence_in_the_frames_own_category_is_found_with_one_search(run_agent):
    final, llm, requests = run_agent([chunk("earned leave rules", "earned_leave")], ["earned_leave"])

    assert categories_asked(requests) == [["earned_leave"]]
    assert final["fallback_level"] == 0 and final["levels_tried"] == [0] and final["retrieval_calls"] == 1
    assert llm.calls.count("RewrittenQuery") == 0 and final["final_answer"]["confidence"] == 0.9


def test_evidence_in_a_sibling_category_is_found_at_level_one(run_agent):
    final, llm, requests = run_agent([chunk("sick leave rules", "sick_leave")], ["earned_leave"])

    assert categories_asked(requests) == [["earned_leave"], ["leave", "earned_leave", "sick_leave"]]
    assert final["fallback_level"] == 1 and final["levels_tried"] == [0, 1]
    assert [c["content"] for c in final["retrieved_context"]] == ["sick leave rules"]
    assert llm.calls.count("RewrittenQuery") == 1                          # the query was rewritten for the retry


def test_evidence_in_an_unrelated_category_is_found_only_at_the_whole_domain_level(run_agent):
    final, llm, requests = run_agent([chunk("salary rules", "payroll")], ["earned_leave"])

    assert categories_asked(requests) == [["earned_leave"], ["leave", "earned_leave", "sick_leave"], None]
    assert final["fallback_level"] == 2 and final["levels_tried"] == [0, 1, 2] and final["retrieval_calls"] == 3
    assert [c["content"] for c in final["retrieved_context"]] == ["salary rules"]
    assert final["final_answer"]["confidence"] == 0.9                       # answered, not "insufficient evidence"


def test_with_no_evidence_anywhere_it_tries_every_level_once_and_then_stops(run_agent):
    final, llm, requests = run_agent([], ["earned_leave"])

    assert len(requests) == 3 and categories_asked(requests)[-1] is None   # terminates: three searches, no more
    assert final["fallback_level"] == 2 and final["levels_tried"] == [0, 1, 2]
    assert final["final_answer"]["confidence"] == 0.0                       # the existing "insufficient evidence" answer
    assert final["final_answer"]["answer"].startswith("I couldn't find enough relevant information")


def test_a_category_with_no_parent_goes_straight_from_its_own_level_to_the_whole_domain(run_agent):
    final, _, requests = run_agent([chunk("salary rules", "payroll")], ["privacy"])
    assert categories_asked(requests) == [["privacy"], None]               # level 1 would have repeated level 0: skipped
    assert final["levels_tried"] == [0, 2] and final["fallback_level"] == 2


def test_the_other_frame_searches_the_whole_domain_and_never_widens(run_agent):
    final, _, requests = run_agent([], [])                                  # "other": no categories
    assert categories_asked(requests) == [None, None]                      # the old retry behaviour: two searches
    assert set(final["levels_tried"]) == {0} and final["fallback_level"] == 0


# ---------------------------------------------------------------- localization off: exactly as before

def test_without_a_search_plan_there_are_two_searches_no_categories_and_no_level_is_recorded(run_agent):
    final, llm, requests = run_agent([], None, localize=False)                    # nothing to find: shows the retry cap

    assert len(requests) == 2 and all("categories" not in r for r in requests)    # the old cap: two searches
    assert final["final_answer"]["answer"].startswith("I couldn't find enough relevant information")
    assert "fallback_level" not in final or final["fallback_level"] is None
    assert not final.get("levels_tried")


def test_without_a_search_plan_evidence_is_still_found_when_it_exists(run_agent):
    final, _, requests = run_agent([chunk("earned leave rules", "earned_leave")], None, localize=False)
    assert len(requests) == 1 and [c["content"] for c in final["retrieved_context"]] == ["earned leave rules"]


def test_each_question_starts_counting_searches_from_zero(run_agent):
    """retrieval_calls is reset by prepare_retrieval, so a second question in the same thread starts at level 0."""
    final, _, requests = run_agent([chunk("earned leave rules", "earned_leave")], ["earned_leave"])
    assert final["retrieval_calls"] == 1
    levels = widen_levels(TAX, "hr", ["earned_leave"])
    agent = build_domain_agent(FakeLLM(), "You are the HR agent.", tools=[], domain_name="hr", retrieval_method=["vector"])
    again = asyncio.run(agent.ainvoke({**final, "messages": [HumanMessage(content="and for next year?")],
                                       "localize_levels": levels, "levels_tried": None, "retrieved_context": []}))
    assert again["retrieval_calls"] == 1 and again["levels_tried"] == [0]


# ---------------------------------------------------------------- the category instructions reach the answering prompt

from app.graph.frames.prompts import parse_category_prompts, build_prompt_texts  # noqa: E402
from app.graph.frames.registry import auto_frames  # noqa: E402

PROMPTS = parse_category_prompts(TAX, {"hr": {
    name: {"scope": f"Scope of {name}.", "check": [f"Check for {name}."], "ask": []}
    for name in ("leave", "earned_leave", "sick_leave", "payroll", "privacy")}})
EARNED_FRAME = next(f for f in auto_frames(TAX, "hr") if f.frame_id == "hr.earned_leave")
BLOCK = build_prompt_texts(EARNED_FRAME, PROMPTS, {}, [], ["earned_leave"])


def system_prompt_of_the_answer(llm):
    return llm.answer_prompts[0][0].content


def test_evidence_from_the_frames_own_category_gets_the_strict_rule(run_agent):
    _, llm, _ = run_agent([chunk("earned leave rules", "earned_leave")], ["earned_leave"], extra={"category_prompts_text": BLOCK})
    prompt = system_prompt_of_the_answer(llm)

    assert "frame hr.earned_leave" in prompt and "- earned_leave: Scope of earned_leave." in prompt
    assert "Answer only from evidence in these categories: earned_leave. Do not borrow a rule from another category." in prompt
    assert prompt.index("Localized answer rules") < prompt.index("Context:")             # before the evidence, not after


def test_evidence_found_only_after_widening_gets_the_widened_rule_not_the_strict_one(run_agent):
    final, llm, _ = run_agent([chunk("sick leave rules", "sick_leave")], ["earned_leave"], extra={"category_prompts_text": BLOCK})
    prompt = system_prompt_of_the_answer(llm)

    assert final["fallback_level"] == 1
    assert "was widened to related parts of the documents" in prompt
    assert "Answer only from evidence in these categories" not in prompt                   # it would contradict the evidence given


def test_whole_domain_evidence_also_gets_the_widened_rule(run_agent):
    final, llm, _ = run_agent([chunk("salary rules", "payroll")], ["earned_leave"], extra={"category_prompts_text": BLOCK})
    assert final["fallback_level"] == 2 and "was widened to related parts" in system_prompt_of_the_answer(llm)


def test_without_prompt_texts_the_answering_prompt_has_no_localized_rules(run_agent):
    _, llm, _ = run_agent([chunk("earned leave rules", "earned_leave")], ["earned_leave"])      # the filter level, or off
    assert "Localized answer rules" not in system_prompt_of_the_answer(llm)


def test_the_block_is_the_only_difference_in_the_answering_prompt(run_agent):
    corpus = [chunk("earned leave rules", "earned_leave")]
    _, plain, _ = run_agent(corpus, ["earned_leave"])
    _, with_block, _ = run_agent(corpus, ["earned_leave"], extra={"category_prompts_text": BLOCK})
    without_the_block = with_block.answer_prompts[0][0].content.replace(BLOCK["strict"] + "\n\n", "")
    assert without_the_block == plain.answer_prompts[0][0].content
