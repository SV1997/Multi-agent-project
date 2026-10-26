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
from .context_policy import split_for_summary,summarize, ledger_text, LEDGER_LABEL, guard_notes
from .memory_policy import IDENTITY_ALIASES, SEMANTIC_LIMIT, build_memory_text, canonical_memory_key, is_negative_fact
import os
from langchain_core.runnables import RunnableConfig
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), "../../../../../.."))
from shared.contracts.schema import HR_SLOTS, Extraction, Fact, MemoryExtraction as Mem0Extraction
from .context_policy import apply_fact, contains_value, fetch_thread_data
from ..core.config import DATABASE_URL
import asyncpg
from .conversation_memory import similar_memories, insert_memory
from . import conversation_memory
from ..core import config as app_config
from shared.taxonomy.taxonomy import load_taxonomy
from .frames.registry import load_registry
from .frames.node import (
    FrameChoice, make_frame_query_node, route_after_authorization, route_after_frame, ask_for_slot,
)
from .frames.dag import make_trace_node
async def get_connection():
    return await asyncpg.connect(DATABASE_URL)
DISABLE_LONG_TERM_MEMORY = os.getenv("DISABLE_LONG_TERM_MEMORY") == "1"
def set_supervisor_agent(checkpointer,store):
    class DomainClassification(BaseModel):
        domain: Literal["legal","hr","engineering","finance","support"] = Field(description="It provide routing detail for the tool base on the literal")
    class MemoryFact(BaseModel):
        topic_key: str = Field(description="Short, stable key identifying the fact's topic.")
        content: str = Field(description="The durable fact itself.")
    class MemoryExtraction(BaseModel):
        facts: list[MemoryFact] = Field(description="Durable facts worth remembering. Empty list if nothing durable.")
    # Free-text classification on gpt-oss-120b intermittently fails with Groq's
    # output_parse_failed (empty generation) and was also inaccurate, so the classifier
    # returns a structured enum instead. The two structured methods fail on different
    # inputs, so classify_domain tries one, then the other, before giving up.
    def _structured_classifier(method: str):
        return (
            init_chat_model(model="groq:openai/gpt-oss-120b", temperature=0, streaming=False, reasoning_effort="low")
            .with_structured_output(DomainClassification, method=method, **({"strict": True} if method == "json_schema" else {}))
            .with_config(tags=["classification-only"])
            .with_retry(stop_after_attempt=2)
        )

    classifier_function_calling = _structured_classifier("function_calling")
    classifier_json_schema = _structured_classifier("json_schema")

    # Query frames (localized search). With LOCALIZE=off nothing is loaded and the frame step does nothing. With it
    # on, the frames are validated against the taxonomy right here, so a mistake in frames.yaml stops the service
    # at startup instead of surfacing later as a strange answer.
    frame_taxonomy = None
    frame_registry = None
    frame_choosers = []
    if app_config.LOCALIZE != "off":
        frame_taxonomy = load_taxonomy()
        frame_registry = load_registry(frame_taxonomy)

        def _frame_chooser(method: str):
            return (
                init_chat_model(model="groq:openai/gpt-oss-120b", temperature=0, streaming=False, reasoning_effort="low")
                .with_structured_output(FrameChoice, method=method, **({"strict": True} if method == "json_schema" else {}))
                .with_config(tags=["frame-choice"])
                .with_retry(stop_after_attempt=2)
            )

        # the two structured-output methods fail on different inputs, as with the domain classifier
        frame_choosers = [("function_calling", _frame_chooser("function_calling")),
                          ("json_schema", _frame_chooser("json_schema"))]
    frame_query = make_frame_query_node(frame_registry, frame_choosers, level=lambda: app_config.LOCALIZE)
    trace_query = make_trace_node(frame_taxonomy, level=lambda: app_config.LOCALIZE)

    summary_llm = (
        init_chat_model(model="groq:openai/gpt-oss-120b", streaming=False, reasoning_effort="high").with_config(tags=["summarization"]).with_retry(stop_after_attempt=3)
    )

    
    memory_extraction_llm = (init_chat_model(model="groq:openai/gpt-oss-120b", temperature=0.2, streaming=False, reasoning_effort="low").
    with_structured_output(MemoryExtraction,method="json_schema", strict=True )
    .with_config(tags=["fetching_memory"])
    .with_retry(stop_after_attempt=3)
    )

    field_extractot_llm = (init_chat_model(model="groq:openai/gpt-oss-120b", temperature=0.2, streaming=False, reasoning_effort="low").
    with_structured_output(Extraction,method="json_schema", strict=True ))

    CLASSIFIER_HISTORY_WINDOW = 6
    async def manage_context(state:AgentState)-> dict:
        messages = state["messages"]
        split=split_for_summary(messages)

        if split is None:
            return {}
        ledger, to_compress, to_remove= split
        old_notes = ledger_text(ledger)if ledger else ""
        new_notes = await summarize(summary_llm, old_notes, to_compress)
        user_text = "\n".join(str(m.content) for m in to_compress if isinstance(m, HumanMessage))
        new_notes, missing = guard_notes(old_notes + "\n" + user_text, new_notes)
        logger.info("LEDGER cycle: %d human turns, %d chars\n%s",
                    len([m for m in state["messages"] if isinstance(m, HumanMessage)]),
                    len(new_notes), new_notes)
        if missing:
            logger.warning("Ledger guard recovered %d identifiers: %s", len(missing), missing)
        return {
            "messages":[RemoveMessage(id=m.id) for m in to_remove]+
            [SystemMessage(content = f"{LEDGER_LABEL} {new_notes}")]
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
                - Statements about MISSING information (for example "no name is on file", "location unknown"). A missing fact is not a fact.

                For the employee's name, location, role and manager use exactly these topic keys: name, location, role, manager.

                If nothing in the answer meets the bar above, return an empty facts list. Most turns should produce zero facts -
                only extract when there is a genuinely durable, employee-specific detail worth recalling in a future conversation.
                """),
                HumanMessage(content=f"User asked: {query}\n\nAssistant answered: {final_answer.get('answer')}")
            ])

            for fact in extraction.facts:
                topic_key=fact.topic_key
                content= fact.content
                if not topic_key or not content or is_negative_fact(content):
                    continue
                topic_key = canonical_memory_key(topic_key)
                await store.aput(
                    (memory_namespace_key(state.get("employee_email")),),
                    topic_key,
                    {"content":content}
                )
        except Exception:
            logger.exception("Background memory extraction failed for employee '%s'.", state.get("employee_email"))
    _background_tasks:set[asyncio.Task] = set()


    async def retrieve_memories(state:AgentState)->dict:
        # if DISABLE_LONG_TERM_MEMORY:
        return {"long_term_memory": None}
        # try:
        #     query = latest_human_query(state)
        #     print(query, 137)
        #     if not query:
        #         return {"long_term_memory":None}
        #     namespace = (memory_namespace_key(state.get("employee_email")),)
        #     # identity facts (name, location, ...) are always loaded; the question only decides the rest
        #     identity, semantic = await asyncio.gather(
        #         asyncio.gather(*(store.aget(namespace, key) for key in IDENTITY_ALIASES)),
        #         store.asearch(namespace, query=query, limit=SEMANTIC_LIMIT),
        #     )
        #     memory_text = build_memory_text(dict(zip(IDENTITY_ALIASES, identity)), semantic)
        #     print(memory_text)
        #     return {"long_term_memory":memory_text}
        # except Exception:
        #     logger.exception("some issue occurred while fetching memories")
        #     return {"long_term_memory":None}


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

    CLASSIFIER_PROMPT = SystemMessage(content="""Classify the user's MOST RECENT message into exactly one domain. Earlier messages are
context only: use them when the latest message is a follow-up that cannot be classified
on its own, otherwise ignore them.

Domains:
- finance: expense claims and reimbursements, salary and CTC, payroll, budgets, invoices
- hr: leave, manager and team changes, joining and exit, benefits, office facilities and amenities, HR policies
- legal: contracts, compliance, regulations, liability, penalties and legal disputes
- engineering: code, deployments, infrastructure, technical documentation
- support: IT helpdesk tickets, hardware or software problems, access issues""")

    async def classify_domain(state: AgentState)-> dict:
        clean_history = [m for m in state["messages"] if _is_clean_conversational_turn(m)]
        last_human = latest_human_query(state)
        history = [CLASSIFIER_PROMPT] + clean_history[-CLASSIFIER_HISTORY_WINDOW:]
        latest_only = [CLASSIFIER_PROMPT, HumanMessage(content=last_human)]
        # The two structured methods fail on different inputs, so try both with recent history,
        # then once more with only the latest message (a smaller, history-independent input).
        attempts = [
            ("function_calling + history", classifier_function_calling, history),
            ("json_schema + history", classifier_json_schema, history),
            ("function_calling + latest message only", classifier_function_calling, latest_only),
        ]
        for label, classifier, messages in attempts:
            try:
                decision = await classifier.ainvoke(messages)
            except GroqAPIError:
                logger.exception(
                    "Groq domain classification failed (%s, %d messages). Last user message: %r",
                    label, len(messages), last_human,
                )
                continue

            domain = getattr(decision, "domain", None)
            if domain is None:
                logger.warning("Domain classification returned no domain (%s): %r", label, decision)
                continue

            print(domain)
            return {
                "domain": domain,
                "classification_failed": False,
            }

        return {"classification_failed": True}

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

    FACT_EXTRACTION_PROMPT = """You extract personal HR facts that the user states about THEMSELVES from a single message.
These facts are saved to a record and used in later turns, so accuracy matters more than coverage.
When in doubt, extract nothing.

SLOTS (the only ones you may use):
- employee_id : the user's own employee ID or staff number (for example "EMP-10492").
- office      : the office, city or building the user works from (for example "Pune", "Building 3").
- seat        : the user's desk or seat location (for example "B-14", "3rd floor, row C").
- manager     : the name of the user's direct manager.

OUTPUT: a list of facts. Each fact has exactly three fields:
- slot     : one of the four slots above.
- value    : the value copied EXACTLY as the user wrote it. Keep letters, digits, hyphens and
             capitalisation. Do not paraphrase, expand, correct or reformat it.
- retracts : true or false, decided separately for every fact (see below).

WHEN TO EXTRACT
- The user states a fact about themselves: "my manager is Priya Rao", "I sit at B-14".
- The user updates a fact: "I moved to seat C-22", "my new manager is Arjun". This is a normal
  fact with retracts=false. The system replaces the old value automatically, so do NOT emit a
  separate retraction for the old value.
- If one message contains several facts, return one entry per fact.

WHEN NOT TO EXTRACT (return an empty list for these)
- Questions or requests: "who is my manager?", "what is the seat policy?", "book me a desk".
- Facts about other people: "Ravi sits at B-14", "my friend's manager is Kiran".
- Hypotheticals, examples and guesses: "if I moved to Delhi...", "maybe seat B-14?", "say my ID were 123".
- General company or policy information that is not specific to the user.
- Anything the user did not say. Never infer, guess or complete a value. If the user says
  "I changed offices" without naming the new office, there is no value, so extract nothing.

RETRACTS
- retracts=false (the default): the user is stating or updating a value.
- retracts=true: the user says a stored value is wrong, no longer true, or asks to forget it:
  "forget my seat", "I no longer have a manager listed", "my office is not Pune anymore".
  - If the user names the value being withdrawn, put that value in `value`.
  - If the user withdraws the slot without naming a value, set `value` to an empty string "".
  - Do not combine them. "my seat is not B-14, it is C-22" is ONE fact: seat = C-22, retracts=false.

EXAMPLES
Message: "Hi, I'm EMP-10492 and I report to Priya Rao."
Output: [{"slot":"employee_id","value":"EMP-10492","retracts":false},
         {"slot":"manager","value":"Priya Rao","retracts":false}]

Message: "I've moved from seat B-14 to C-22."
Output: [{"slot":"seat","value":"C-22","retracts":false}]

Message: "Please forget my seat, I don't have one now."
Output: [{"slot":"seat","value":"","retracts":true}]

Message: "How many leave days do I have left?"
Output: []

Message: "Ravi from finance sits at B-14, can you check who his manager is?"
Output: []"""
    async def extract_facts(state: AgentState, config: RunnableConfig) -> dict:
        thread_id = config["configurable"]["thread_id"]
        user_text = latest_human_query(state)
        if not user_text:
            return {}

        try:
            result = await field_extractot_llm.ainvoke([
                SystemMessage(content=FACT_EXTRACTION_PROMPT),
                HumanMessage(content=user_text),
            ])
            facts = [
                f for f in result.facts
                if f.slot in HR_SLOTS and (f.value.strip() or f.retracts)
            ]
        except Exception:
            # Don't return here: the facts saved in earlier turns still need loading below.
            logger.exception("Fact extraction failed. Last user message: %r", user_text)
            facts = []

        for f in facts:
            if f.value.strip() and not contains_value(user_text, f.value):
                logger.warning("Dropping ungrounded fact %s=%r (not in user text)", f.slot, f.value)
                continue
            try:
                outcome = await apply_fact(
                    thread_id=thread_id, slot=f.slot, value=f.value,
                    retracts=f.retracts, turn_id=state.get("turn"), source_text=user_text,
                )
                logger.info("apply_fact %s=%r retracts=%s -> %s", f.slot, f.value, f.retracts, outcome)
            except Exception:
                logger.exception("apply_fact failed for slot %r on thread %r", f.slot, thread_id)
        try:
            return {"thread_facts": await fetch_thread_data(thread_id)}
        except Exception:
            logger.exception("Could not load thread facts for thread %r", thread_id)
            return {}
    async def memory_search(state: AgentState, config: RunnableConfig) -> dict:
        if conversation_memory.memory_mode() != "memory":
            return {}
        stats = conversation_memory.MEMORY_STATS
        stats["search_calls"] += 1
        try:
            query = latest_human_query(state)
            if not query:
                return {"conversation_memories": None}
            thread_id = config["configurable"]["thread_id"]
            rows = await conversation_memory.search_memories(
                state.get("employee_email") or "unknown", thread_id, query)
            return {"conversation_memories": conversation_memory.render_memories(rows) or None}
        except Exception:
            stats["search_failures"] += 1
            logger.exception("Conversation memory search failed; answering without it.")
            return {"conversation_memories": None} 

    async def _memory_add(state: AgentState, config: RunnableConfig) -> dict:
        if conversation_memory.memory_mode() != "memory":
            return {}
        stats = conversation_memory.MEMORY_STATS
        stats["add_calls"] += 1
        try:
            message = latest_human_query(state)
            if not message:
                return {}
            thread_id = config["configurable"]["thread_id"]
            results = await conversation_memory.add_memories(
                state.get("employee_email") or "unknown", thread_id, message,
                conversation_memory.recent_text(state["messages"]), state.get("turn"))
            stats["extracted"] += len(results)
            for r in results:
                stats[r["status"]] += 1
                stats["bad_link"] += len(r["bad_links"])
        except Exception:
            stats["add_failures"] += 1
            logger.exception("Conversation memory add failed; the answer is unaffected.")
        return {}
    async def memory_add(state: AgentState, config: RunnableConfig) -> dict:
        task = asyncio.create_task(_memory_add(state,config))
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)
        return {}

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
    # graph.add_node("extract_facts",extract_facts)
    graph.add_node("memory_search",memory_search)
    graph.add_node("memory_add",memory_add)
    graph.add_node("frame_query", frame_query)
    graph.add_node("ask_for_slot", ask_for_slot)
    graph.add_node("trace_query", trace_query)
    graph.add_edge(START,"manage_context")
    graph.add_edge(START,"retrieve_memories")
    graph.add_edge(START,"memory_search")
    graph.add_edge("memory_search","classify_domain")
    graph.add_edge("manage_context","classify_domain")
    graph.add_edge("retrieve_memories","classify_domain")
    # graph.add_edge("extract_facts","classify_domain")
    graph.add_conditional_edges(
        "classify_domain", route_after_classification, {
            "ok": "check_authorization",
            "failed": "classification_failed",
        }
    )
    # authorized -> frame_query (a no-op with LOCALIZE=off) -> the domain's agent, or a clarifying question
    graph.add_conditional_edges(
        "check_authorization", route_after_authorization, {
            "frame": "frame_query",
            "denied": "access_denied"
        }
    )
    graph.add_conditional_edges(
        "frame_query", route_after_frame, {
            "legal":"legal_agent",
            "hr" : "hr_agent",
            "finance": "finance_agent",
            "support": "support_agent",
            "engineering": "engineering_agent",
            "ask": "ask_for_slot"
        }
    )
    graph.add_edge("ask_for_slot", END)
    graph.add_edge("finance_agent", "human_review_gate")
    graph.add_edge("legal_agent", "human_review_gate")
    graph.add_edge("hr_agent", "human_review_gate")
    graph.add_edge("engineering_agent", "human_review_gate")
    graph.add_edge("support_agent", "human_review_gate")
    graph.add_edge("human_review_gate", "trace_query")
    graph.add_edge("trace_query", "memory_add")
    graph.add_edge("memory_add","extract_memories")
    graph.add_edge("extract_memories",END)
    graph.add_edge("access_denied", END)
    graph.add_edge("classification_failed", END)
    return graph.compile(checkpointer=checkpointer)
 




