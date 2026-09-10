import logging
from langgraph.graph import StateGraph, START, END
from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
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
from .agents.coding_agent.graph import coding_agent
from langgraph.checkpoint.memory import MemorySaver
from .hitl.interrupts import human_review_gate
import asyncio


def set_supervisor_agent(checkpointer,store):
    class DomainClassification(BaseModel):
        domain: Literal["legal","hr","engineering","coding","support"] = Field(description="It provide routing detail for the tool base on the literal")
    class MemoryExtraction(BaseModel):
        facts: list[dict] = Field(description="List of {'topic_key': str, 'content': str} for durable facts worth remembering. Empty list if nothing durable.")
    classifier_llm = (
        init_chat_model(model="groq:openai/gpt-oss-120b", temperature=0.2, streaming=False, reasoning_effort="low")
        .with_structured_output(DomainClassification, method="json_schema", strict=True)
        .with_config(tags=["classification-only"])
        .with_retry(stop_after_attempt=3)
    )

    summary_llm = (
        init_chat_model(model="groq:openai/gpt-oss-120b", streaming=False, reasoning_effort="high").with_config(tags=["summarization"]).with_retry(stop_after_attempt=3)
    )

    memory_extraction_llm = (init_chat_model(model="groq:openai/gpt-oss-120b", temperature=0.2, streaming=False).
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

    async def _extract_memories_task(state:AgentState)-> None:
        answer = (
                    "I couldn't find enough relevant information in the authorized knowledge base "
                    "to answer this reliably. Please provide a more specific question or ask an "
                    "authorized reviewer for help."
                )
        try:
            final_answer = state.get("final_answer") or{}
            if(final_answer.get("confidence",0.0)<=0.3):
                        return
            extraction = await memory_extraction_llm.ainvoke([
                SystemMessage(content="""From the finalisez answer generated from the current user query extract the facts, any key words, that are important for further use and will stay consistent 
                for the chat in future. if use asks to store anything specifically store that infromationn too.
                Don't extact the error messages 
                1. if the agents failed to answer, 
                2. Domain classification failed, 
                3. any issue if the service or api failed to answer,
                4. or any agent denied to answer or 
                5. kept in loop for human review
                6. insufficient evidence
                don't extract them.
                """),
                HumanMessage(content=f"the answer generated from user query is {state.get('final_answer').get("answer")}")
            ])

            for fact in extraction.facts:
                topic_key=fact.get("topic_key")
                content= fact.get("content")
                if not topic_key or not content:
                    continue
                await store.aput(
                    (state.get("employee_email"),),
                    topic_key,
                    {"content":content}
                )
        except Exception:
            logger.exception(("Background memory extraction failed for employee '%s'.", state.get("employee_email")))
    _background_tasks:set[asyncio.Task] = set()


    async def retrieve_memories(state:AgentState)->dict:
        query = latest_human_query(state)
        if not query:
            return {"long_term_memory":None}
        results = await store.asearch(
            (state.get("employee_email"),),
            query = query,
            limit=3
        )
        if not results:
            return {"long_term_memory":None}
        memory_text = "\n".join(r.value.get("content","") for r in results)
        return {"long_term_memory":memory_text}

    async def extract_memories(state:AgentState)-> dict:
        task = asyncio.create_task(_extract_memories_task(state))
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)
        return{}

    async def classify_domain(state: AgentState)-> dict:
        prompt = SUPERVISOR_ROUTE_PROMPT

        messages = [SystemMessage(content=prompt)] + state["messages"][-CLASSIFIER_HISTORY_WINDOW:]

        # Groq's json_schema-strict structured output occasionally comes back
        # with an unparsable (sometimes empty) generation for this reasoning
        # model; with_retry absorbs that transient flake instead of failing
        # the whole turn. If all retries are exhausted, fail soft into
        # classification_failed instead of crashing the turn - we can't pick
        # an authorized domain to route to without a real classification.
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
    graph.add_node("coding_agent", coding_agent)
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
            "coding": "coding_agent",
            "support": "support_agent",
            "engineering": "engineering_agent",
            "denied": "access_denied"
        }
    )
    graph.add_edge("coding_agent", "human_review_gate")
    graph.add_edge("legal_agent", "human_review_gate")
    graph.add_edge("hr_agent", "human_review_gate")
    graph.add_edge("engineering_agent", "human_review_gate")
    graph.add_edge("support_agent", "human_review_gate")
    graph.add_edge("human_review_gate", "extract_memories")
    graph.add_edge("extract_memories",END)
    graph.add_edge("access_denied", END)
    graph.add_edge("classification_failed", END)
    return graph.compile(checkpointer=checkpointer)
 




