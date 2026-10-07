import logging
from langgraph.graph import StateGraph, START, END
from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
from pydantic import BaseModel, Field
from typing import Literal
from groq import APIError as GroqAPIError
from .state import AgentState
from langchain_core.messages import RemoveMessage
logger = logging.getLogger(__name__)
from .prompts.supervisor_routing import SUPERVISOR_ROUTE_PROMPT
from .agents.legal_agent.graph import legal_agent
from .prompts.supervisor_routing import SUPERVISOR_ROUTE_PROMPT
from .agents.hr_agent.graph import hr_agent
from .agents.engineering_agent.graph import engineering_agent
from .agents.support_agent.graph import support_agent
from .agents.finance_agent.graph import finance_agent
from langgraph.checkpoint.memory import MemorySaver
from .hitl.interrupts import human_review_gate
import asyncio


def set_supervisor_agent(checkpointer,store):
    class DomainClassification(BaseModel):
        domain: Literal["legal","hr","engineering","finance","support"] = Field(description="It provide routing detail for the tool base on the literal")
    class MemoryFact(BaseModel):
        topic_key: str = Field(description="Short, stable key identifying the fact's topic.")
        content: str = Field(description="The durable fact itself.")
    class MemoryExtraction(BaseModel):
        facts: list[MemoryFact] = Field(description="Durable facts worth remembering. Empty list if nothing durable.")
    # Untried lever for the recurring output_parse_failed on this call:
    # method="json_schema" uses Groq's strict constrained-decoding path;
    # method="function_calling" goes through Groq's tool-calling path
    # instead, which behaves differently under the same input and has
    # empirically been more robust for other structured calls in this
    # codebase. streaming=False/reasoning_effort="low" were already set
    # and didn't fully resolve this, and history is already filtered of
    # tool-call artifacts (see _is_clean_conversational_turn below) - this
    # is the next thing to try, not a confirmed fix.
    classifier_llm = (
        init_chat_model(model="groq:openai/gpt-oss-120b", temperature=0.2, streaming=False, reasoning_effort="low")
        .with_structured_output(DomainClassification, method="function_calling")
        .with_config(tags=["classification-only"])
        .with_retry(stop_after_attempt=3)
    )

    summary_llm = (
        init_chat_model(model="groq:openai/gpt-oss-120b", streaming=False, reasoning_effort="high").with_config(tags=["summarization"]).with_retry(stop_after_attempt=3)
    )

    memory_extraction_llm = (init_chat_model(model="groq:openai/gpt-oss-120b", temperature=0.2, streaming=False, reasoning_effort="low").
    with_structured_output(MemoryExtraction,method="json_schema", strict=True )
    .with_config(tags=["fetching_memory"])
    .with_retry(stop_after_attempt=3)
    )

    CLASSIFIER_HISTORY_WINDOW = 6
    SUMMARIZE_THRESHOLD = 12
    KEEP_RAW_TURNS = 5
    async def manage_context(state:AgentState)-> dict:
        messages = state["messages"]
        human_turns = [m for m in messages if isinstance(m,HumanMessage)]
        if len(human_turns)<= SUMMARIZE_THRESHOLD:
            return {}

        keep_from_human_turn = human_turns[-KEEP_RAW_TURNS]
        cut_off_index = messages.index(keep_from_human_turn)
        message_to_summarize = messages[:cut_off_index]
        message_to_keep = messages[cut_off_index:]

        summary = await summary_llm.ainvoke([
            SystemMessage(content="you have a list of messages summarize them, preserve the key facts, names, decision and details, question keeped for review and unresolved querie "),
            *message_to_summarize

        ])

        return {
            "messages":[RemoveMessage(id=m.id) for m in message_to_summarize]+
            [SystemMessage(content = f"[Earlier conversation ummary]: {summary.content}")]
        }

    def latest_human_query(state: AgentState) -> str:
        human_messages = [message for message in state["messages"] if isinstance(message, HumanMessage)]
        return human_messages[-1].content if human_messages else ""

    def memory_namespace_key(employee_email: str | None) -> str:
        # langgraph's store rejects '.' in namespace labels, but every
        # employee email has one - this was silently failing on every
        # store.aput/asearch call, so long-term memory never actually
        # stored or retrieved anything.
        return (employee_email or "").replace(".", "_")

    async def _extract_memories_task(state:AgentState)-> None:
        try:
            final_answer = state.get("final_answer") or{}
            if(final_answer.get("confidence",0.0)<=0.3):
                        return
            query = latest_human_query(state)
            extraction = await memory_extraction_llm.ainvoke([
                SystemMessage(content="""You are extracting long-term memory for a specific employee from one Q&A turn.

                Only extract facts that are:
                - Specific to this employee (their situation, preferences, decisions, commitments, or personal identifiers), OR
                - Something the user explicitly asked to be remembered.

                Do NOT extract:
                - General knowledge-base or policy content restated in the answer (e.g. "the leave policy allows 12 days") unless
                  it is tied to a fact about this employee specifically (e.g. "the employee has 5 leave days remaining").
                - Anything that is just a paraphrase or summary of the answer text.
                - Error states: the agent failed to answer, domain classification failed, an upstream service/API failed,
                  the agent declined to answer, the turn is pending human review, or there was insufficient evidence.

                If nothing in the answer meets the bar above, return an empty facts list. Most turns should produce zero facts -
                only extract when there is a genuinely durable, employee-specific detail worth recalling in a future conversation.
                """),
                HumanMessage(content=f"User asked: {query}\n\nAssistant answered: {final_answer.get('answer')}")
            ])

            for fact in extraction.facts:
                topic_key=fact.topic_key
                content= fact.content
                if not topic_key or not content:
                    continue
                await store.aput(
                    (memory_namespace_key(state.get("employee_email")),),
                    topic_key,
                    {"content":content}
                )
        except Exception:
            logger.exception("Background memory extraction failed for employee '%s'.", state.get("employee_email"))
    _background_tasks:set[asyncio.Task] = set()


    async def retrieve_memories(state:AgentState)->dict:
        try:
            query = latest_human_query(state)
            print(query, 137)
            if not query:
                return {"long_term_memory":None}
            results = await store.asearch(
                (memory_namespace_key(state.get("employee_email")),),
                query = query,
                limit=3
            )
            print(results, "145")
            if not results:
                return {"long_term_memory":None}
            memory_text = "\n".join(r.value.get("content","") for r in results)
            print(memory_text)
            return {"long_term_memory":memory_text}
        except Exception:
            logger.exception("some issue occurred while fetching memories")
            return {"long_term_memory":None}


    async def extract_memories(state:AgentState)-> dict:
        task = asyncio.create_task(_extract_memories_task(state))
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)
        return{}

    def _is_clean_conversational_turn(m) -> bool:
        if isinstance(m, ToolMessage):
            return False
        if isinstance(m, AIMessage) and getattr(m, "tool_calls", None):
            return False
        return True

    async def classify_domain(state: AgentState)-> dict:
        prompt = SUPERVISOR_ROUTE_PROMPT

        clean_history = [m for m in state["messages"] if _is_clean_conversational_turn(m)]
        messages = [SystemMessage(content=prompt)] + clean_history[-CLASSIFIER_HISTORY_WINDOW:]
        try:
            decision = await classifier_llm.ainvoke(messages)
        except GroqAPIError:
            last_human = next(
                (m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
                "",
            )
            logger.exception(
                "Groq domain-classification generation failed to parse. "
                "Last user message: %r", last_human
            )
            return {"classification_failed": True}

        print(decision.domain)

        return{
            "domain": decision.domain,
            "classification_failed": False,
        }

    def route_after_classification(state: AgentState) -> str:
        if state.get("classification_failed"):
            return "failed"
        return "ok"

    def classification_failed(state: AgentState) -> dict:
        answer = (
            "I couldn't understand this request well enough to route it. "
            "Please rephrase your question."
        )
        return {
            "messages": [AIMessage(content=answer)],
            "final_answer": {
                "domain": "unclassified",
                "answer": answer,
                "sources": [],
                "confidence": 0.0,
                "requires_human_review": False,
            },
        }

    def check_authorization(state:AgentState)->dict:
        allowed = state.get("allowed_namespace") or []
        classified_domains = [state["domain"]]
        print(allowed, classified_domains)
        unauthorized = [d for d in classified_domains if d not in allowed]
        if(unauthorized):
            return {"authorization_denied": True, "denied_domain":unauthorized}
        return {"authorization_denied": False}

    def route_to_agent(state:AgentState)-> str:
        if state.get("authorization_denied"):
            return "denied"
        return state["domain"]

    def access_denied(state: AgentState) -> dict:
        denial_text = "This query touches a domain you are not authorized to access."
        return {
        "messages": [AIMessage(content=denial_text)],
        "final_answer": {
            "domain": state.get("domain"),
            "answer": denial_text,
            "sources": [],
            "confidence": 1.0,
            "requires_human_review": False,
        }
    }
        

    graph = StateGraph(AgentState)
    graph.set_entry_point("manage_context")
    graph.add_node("retrieve_memories",retrieve_memories)
    graph.add_node("manage_context",manage_context)
    graph.add_node("classify_domain", classify_domain)
    graph.add_node("check_authorization", check_authorization)
    graph.add_node("legal_agent", legal_agent)
    graph.add_node("hr_agent", hr_agent)
    graph.add_node("engineering_agent", engineering_agent)
    graph.add_node("support_agent", support_agent)
    graph.add_node("finance_agent", finance_agent)
    graph.add_node("human_review_gate",human_review_gate)
    graph.add_node("access_denied",access_denied)
    graph.add_node("classification_failed",classification_failed)
    graph.add_node("extract_memories",extract_memories)
    graph.add_edge(START,"manage_context")
    graph.add_edge(START,"retrieve_memories")
    graph.add_edge("manage_context","classify_domain")
    graph.add_edge("retrieve_memories","classify_domain")
    graph.add_conditional_edges(
        "classify_domain", route_after_classification, {
            "ok": "check_authorization",
            "failed": "classification_failed",
        }
    )
    graph.add_conditional_edges(
        "check_authorization", route_to_agent,{
            "legal":"legal_agent",
            "hr" : "hr_agent",
            "finance": "finance_agent",
            "support": "support_agent",
            "engineering": "engineering_agent",
            "denied": "access_denied"
        }
    )
    graph.add_edge("finance_agent", "human_review_gate")
    graph.add_edge("legal_agent", "human_review_gate")
    graph.add_edge("hr_agent", "human_review_gate")
    graph.add_edge("engineering_agent", "human_review_gate")
    graph.add_edge("support_agent", "human_review_gate")
    graph.add_edge("human_review_gate", "extract_memories")
    graph.add_edge("extract_memories",END)
    graph.add_edge("access_denied", END)
    graph.add_edge("classification_failed", END)
    return graph.compile(checkpointer=checkpointer)
 




