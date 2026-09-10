from langgraph.graph import StateGraph, START, END
from ...state import AgentState
from langgraph.prebuilt import ToolNode
from langchain.messages import HumanMessage, SystemMessage, AIMessage
from pydantic import BaseModel, Field
from .nodes import retrieve_context, build_context_prompt
import sys
import os
import logging
from groq import APIError as GroqAPIError
from langchain_core.callbacks import adispatch_custom_event
sys.path.append(os.path.join(os.path.dirname(__file__), "../../../../../.."))
from .nodes import retrieve_sql_context
from shared.contracts.schema import AgentAnswer, AgentAnswerLLM, RetrievalAssessment, RetrievalPlan, RewrittenQuery, SQLQuerySelection

logger = logging.getLogger(__name__)

def route_after_reason(state:AgentState)-> str:
    msg = state["messages"][-1]
    if hasattr(msg, "tool_calls") and msg.tool_calls:
        if state["tool_calls_remaining"]>0:
            return "tools"
        # Out of tool calls but the model still emitted one (unexecuted) -
        # loop back to force a final, tool-less answer instead of ending
        # on an empty-content message.
        return "reason"
    return "end"


SQL_FUNCTION_DESCRIPTIONS = {
    "leave_balance": "the user's remaining leave/vacation days",
    "CTC_data": "the user's compensation/CTC figure",
    "get_ticket_status": "status of the user's most recent support ticket",
    "contract_tracking": "status/details of a specific legal contract, identified by contract number",
    "deployment_status": "status of the user's most recent deployment",
}
def build_domain_agent(llm,system_prompt:str, tools: list = None, domain_name: str = "", retrieval_method: list[str] = None, sql_function:list[str]=None):
    tool = tools or []
    retrieval_method = retrieval_method or []
    graph = StateGraph(AgentState)
    print(retrieval_method)

    # ChatGroq._agenerate streams whenever self.streaming=True, regardless of
    # response_format - it never consults the library's own _should_stream
    # override that's supposed to skip streaming for json_schema/json_object.
    # Streaming a strict-schema completion is far more failure-prone (Groq
    # validates/reconstructs the constrained JSON incrementally across
    # chunks), so structured-output calls get a non-streaming copy of the
    # model instead of the (possibly streaming) llm passed in. They also get
    # reasoning_effort="low": these are small classification/extraction
    # tasks, and an unset (heavier default) reasoning effort lets the model
    # burn its whole output-token budget on the reasoning trace, leaving
    # nothing for the actual JSON - Groq then reports output_parse_failed
    # with an empty failed_generation.
    structured_output_llm = llm.model_copy(update={"streaming": False, "reasoning_effort": "low"})
    # Sql_structured_llm additionally has to extract free-text values (e.g. a
    # contract number) into params, not just pick a literal - reasoning_effort
    # "low" was causing it to skip that extraction and emit params={}. Keep
    # it non-streaming (still fixes the parse-failure flake) but leave
    # reasoning effort at the model's default.
    sql_selection_llm = llm.model_copy(update={"streaming": False})

    # Groq's json_schema-strict structured output occasionally comes back
    # unparsable for these reasoning models; with_retry absorbs that
    # transient flake instead of failing the whole node.
    retrieval_grader = structured_output_llm.with_structured_output(
        RetrievalAssessment, method="json_schema", strict=True
    ).with_config(tags=["retrieval-grade"]).with_retry(stop_after_attempt=3)
    query_rewriter = structured_output_llm.with_structured_output(
        RewrittenQuery, method="json_schema", strict=True
    ).with_config(tags=["query-rewrite"]).with_retry(stop_after_attempt=3)

    retrieval_planner = structured_output_llm.with_structured_output(RetrievalPlan,method="json_schema", strict=True).with_config(tags=["selecting-retriever"]).with_retry(stop_after_attempt=3)
    Sql_structured_llm = sql_selection_llm.with_structured_output(SQLQuerySelection, method="json_schema", strict=True).with_config(tags=["sql-retriever"]).with_retry(stop_after_attempt=3)
    async def plan_retrieval(state)-> dict:
        available_ret = ", ".join(retrieval_method) or "none"
        prompt = f"""You choose the retrieval method this agent should use to answer the user's question.
        Pick exactly one source from: none, sql, vector.

        - sql: the question asks about a specific person's or entity's live, current, absolute
          data - a number, balance, status, or record that changes over time and belongs to one
          individual (e.g. "how many leaves/days do I have", "what's my balance", "status of my
          request", "for employee E1042"). If the question refers to "my"/"I" and asks for a
          concrete figure or status, prefer sql over none.
          Ticket-record rule: ALWAYS choose sql when the user asks about an existing support
          ticket, including "my ticket", "latest ticket", a ticket ID, or a ticket's current
          status/details (open, pending, resolved, rejected, or similar). Never choose none or
          vector for a request that needs the user's actual ticket record.
        - vector: the question is about static, general reference material - policy, process,
          documentation, how-to, definitions - the kind of content that lives in a knowledge base
          and doesn't depend on which specific person is asking. For tickets, choose vector only
          for general ticket policy, workflow, SLA, escalation, or documentation questions that
          do not ask for an actual ticket record or its current status.
        - none: only for questions answerable from general knowledge with no lookup at all
          (greetings, clarifying questions, or facts that aren't domain- or person-specific).

        This agent is described as follows - use it to judge what counts as "specific data" for sql:
        {system_prompt}

        Only choose a source that is actually available to this agent: {available_ret}.
        """

        assessment =await retrieval_planner.ainvoke([
            SystemMessage(content=(prompt)),
            HumanMessage(content=(f"Available sources: {available_ret}\n\nUser question: {state.get('original_query', '')}"))
        ])
        source = assessment.source
        if source=="sql" and "sql" not in retrieval_method:
            source ="vector" if "vector" in retrieval_method else "none"
        return {"retrieval_source":source, "retrieval_plan_reason":assessment.reason}
        

    def latest_human_query(state: AgentState) -> str:
        human_messages = [message for message in state["messages"] if isinstance(message, HumanMessage)]
        return human_messages[-1].content if human_messages else ""

    async def prepare_retrieval(state: AgentState) -> dict:
        """Reset retrieval state once per incoming user turn."""
        query = latest_human_query(state)
        return {
            "original_query": query,
            "search_query": query,
            "retrieval_attempts": 0,
            "max_retrieval_attempts": 3,
            "retrieval_quality": None,
            "retrieval_assessment": None,
            "retrieval_can_use_tool": False,
        }

    async def grade_retrieval(state: AgentState) -> dict:
        chunks = state.get("retrieved_context") or []
        # Keep the grading prompt bounded: grading is evidence selection, not
        # another full answer-generation pass.
        evidence = "\n\n".join(
            f"[Source {index}: {chunk.get('source', 'unknown')}]\n{chunk.get('content', '')[:1200]}"
            for index, chunk in enumerate(chunks, 1)
        ) or "No passages were returned."
        available_tools = "\n".join(
            f"- {available_tool.name}: {available_tool.description}"
            for available_tool in tool
        ) or "No live tools are available."
        assessment = await retrieval_grader.ainvoke([
            SystemMessage(content=(
                "You grade retrieval evidence for a RAG assistant. Mark it relevant only "
                "when the passages contain factual support for answering the user's actual "
                "question. Do not treat a merely related topic as sufficient evidence. "
                "Set can_be_answered_by_tool to true only if a listed live tool directly "
                "performs the action requested by the user; otherwise set it to false."
            )),
            HumanMessage(content=(
                f"Original question: {state.get('original_query', '')}\n"
                f"Search query used: {state.get('search_query', '')}\n\n"
                f"Available live tools:\n{available_tools}\n\n"
                f"Retrieved passages:\n{evidence}"
            )),
        ])
        return {
            "retrieval_quality": "relevant" if assessment.relevant else "insufficient",
            "retrieval_assessment": assessment.reason,
            "retrieval_can_use_tool": assessment.can_be_answered_by_tool,
        }

    async def rewrite_query(state: AgentState) -> dict:
        retrieval_attempts = state.get("retrieval_attempts",0)+1
        rewritten = await query_rewriter.ainvoke([
            SystemMessage(content=(
                "Rewrite the user's question for vector retrieval. Preserve all named entities, "
                "employee IDs, dates, and constraints. Return only a search query; do not answer."
            )),
            HumanMessage(content=(
                f"Original question: {state.get('original_query', '')}\n"
                f"Previous search query: {state.get('search_query', '')}\n"
                f"Why it was insufficient: {state.get('retrieval_assessment', '')}"
            )),
        ])
        return {"search_query": rewritten.search_query, "retrieval_attempts":retrieval_attempts}

    def route_after_sql(state: AgentState) -> str:
        # SQL retrieval is deterministic - the only "insufficient" case is an
        # actual error (unknown/misrouted function), not a fuzzy relevance
        # call, so no LLM grading is needed here. A clean "no record found"
        # result is a legitimate answer and is left to reason() to report.
        chunks = state.get("retrieved_context") or []
        if any(chunk.get("source") == "sql:error" for chunk in chunks):
            return "insufficient_evidence"
        return "reason"

    def route_after_grading(state: AgentState) -> str:
        if state.get("retrieval_quality") == "relevant" or state.get("retrieval_can_use_tool"):
            return "reason"
        exhausted= state.get("retrieval_attempts", 0) >= state.get("max_retrieval_attempts", 3)
        if not exhausted and state.get("retrieval_source")=="vector":
            return "rewrite_query"
        if not state.get("fallback_used") and "sql" in retrieval_method and "vector" in retrieval_method:
            current = state.get("retrieval_source")
            if current == "sql":
                return "fallback_to_vector"
            elif current == "vector" and exhausted:
                return "fallback_to_sql"
        return "insufficient_evidence"

    def insufficient_evidence(state: AgentState) -> dict:
        answer = (
            "I couldn't find enough relevant information in the authorized knowledge base "
            "to answer this reliably. Please provide a more specific question or ask an "
            "authorized reviewer for help."
        )
        return {
            "messages": [AIMessage(content=answer)],
            "final_answer": {
                "domain_name": domain_name,
                "answer": answer,
                "sources": [],
                "confidence": 0.0,
                "requires_human_review": False,
            },
            "requires_human_review": False,
        }

    def route_after_planning(state:AgentState)-> str:
        source = state.get("retrieval_source")
        print(source)
        if(source =="sql"):
            return "sql_retrieval"
        elif(source=="vector"):
            return "vector_retrieval"
        else: 
            return "none"
    async def sql_retrieve(state:AgentState)->dict:
        function_list = "\n".join(f"{i}. {name} - {SQL_FUNCTION_DESCRIPTIONS[name]}" for i,name in enumerate(sql_function, 1))
        res = await Sql_structured_llm.ainvoke(
            [
                SystemMessage(content=f"""
                Choose exactly one SQL function that directly answers the user's query.
                query_names are:
                {function_list}
                you have to choose from above provded functions only
Pick the single function that most directly answers the question.
For any query about the user's ticket, latest ticket, existing ticket, ticket ID, or
ticket status, ALWAYS choose get_ticket_status. Never choose another function for a
ticket-record query.
For contract_tracking, include params={{"contract_number": "<the number mentioned>"}}.
For all other functions, params should be empty ({{}}).
Never invent a contract number that is not explicitly present in the question.
                
"""),
                HumanMessage(content=f"{state.get("search_query")}")
            ]
        )
        if res.query_name not in sql_function:
            return {"retrieved_context": [{"source": "sql:error", "content": "Selected function is not available for this domain."}]}
        
        sql_result= await retrieve_sql_context(state, res.query_name, res.params)
        return sql_result

    async def fallback_to_vector(state:AgentState)->dict:
        return {"retrieval_source":"vector", "retrieval_attempts":0, "fallback_used":True}

    async def fallback_to_sql(state:AgentState)->dict:
        return {"retrieval_source":"sql", "retrieval_attempts":0, "fallback_used":True}

    graph.add_node("sql_retrieval", sql_retrieve)
    graph.add_node("plan_retrieval",plan_retrieval)
    graph.add_node("retrieve", retrieve_context)
    graph.add_node("prepare_retrieval", prepare_retrieval)
    graph.add_node("grade_retrieval", grade_retrieval)
    graph.add_node("rewrite_query", rewrite_query)
    graph.add_node("fallback_to_vector",fallback_to_vector)
    graph.add_node("fallback_to_sql",fallback_to_sql)
    graph.add_node("insufficient_evidence", insufficient_evidence)
    structured_llm = structured_output_llm.with_structured_output(AgentAnswerLLM, method="json_schema", strict=True).with_config(tags=["metadata-only"]).with_retry(stop_after_attempt=3)
    # Its output is only ever inspected for .tool_calls - the actual answer
    # text (when no tool is called) comes from a separate plain_llm call
    # below - so it doesn't need to stream, and gets the same non-streaming,
    # low-reasoning-effort treatment as the other structured/decision calls.
    llm_with_tools = (structured_output_llm.bind_tools(tools) if tool else structured_output_llm).with_config(tags=["tool-decision"])
    # Leaving tools unbound here isn't enough to stop tool-call generation:
    # once the conversation history contains a prior AIMessage(tool_calls=...)
    # / ToolMessage pair (from an earlier tool execution this turn), the
    # model pattern-continues in tool-call format even with no tools
    # attached to this request, and Groq rejects it ("Tool choice is none,
    # but model called a tool") since there's nothing to validate the call
    # against. Binding the tools with tool_choice="none" instead lets Groq
    # actively constrain decoding to block tool-call tokens.
    plain_llm = (llm.bind_tools(tools, tool_choice="none") if tool else llm).with_config(tags=["final-answer"])

    async def safe_plain_answer(messages):
        """plain_llm.ainvoke with a graceful fallback if Groq still rejects
        the generation (e.g. tool-call-shaped output despite tool_choice="none")."""
        try:
            return await plain_llm.ainvoke(messages)
        except GroqAPIError:
            logger.exception(
                "Groq final-answer generation failed for domain '%s'.", domain_name
            )
            return AIMessage(content=(
                "I ran into a technical issue generating a response. "
                "Please try rephrasing your question."
            ))

    async def reason(state:AgentState)-> dict:

        context = build_context_prompt(state)
        remaining = state["tool_calls_remaining"]
        long_term_memory = state.get("long_term_memory")
        messages = [
            SystemMessage(content=(
                f"{system_prompt}\n\n"
                "When you call a tool, report exactly what the tool returns. "
                "Never invent specific facts (numbers, dates, names, statuses) "
                "that are not present in the tool output or the retrieved "
                "context below. If a tool result indicates the data isn't "
                "available (e.g. not implemented, empty, or an error), say so "
                "plainly instead of guessing an answer.\n\n"
                f"the long term memory that need to be refered to answer is {long_term_memory}"
                f"Context:{context}"
            ))
            ] + state["messages"]

        # Once out of tool calls, force a final natural-language answer
        # instead of letting the model emit another (unexecuted) tool call.
        sources = [chunk.get("source", "unknown") for chunk in state.get("retrieved_context") or []]
        if remaining<=0:
            answer = await safe_plain_answer(messages)
            return await _finalize_answer(answer, messages, domain_name, sources, remaining)

        try:
            res = await llm_with_tools.ainvoke(messages)
        except GroqAPIError:
            logger.exception(
                "Groq tool-decision generation failed to parse for domain '%s'; "
                "falling back to a tool-less answer.", domain_name
            )
            answer_response = await safe_plain_answer(messages)
            return await _finalize_answer(answer_response, messages, domain_name, sources, remaining)

        if res.tool_calls:
            tool_names = [tc["name"] for tc in res.tool_calls]
            await adispatch_custom_event("tool_call", {"tool_call": tool_names})
            return {"messages":[res], "tool_calls_remaining":remaining-1}

            


        answer_response = await safe_plain_answer(messages)

        return await _finalize_answer(answer_response, messages, domain_name, sources, remaining)
    
    async def _finalize_answer(answer_response,  messages, domain_name, sources, remaining):
        """
    Shared final step for BOTH Case A and Case B.
    answer_response: the AIMessage containing the natural-language answer 
                      (already generated, either by plain llm or by 
                      llm_with_tools when it chose not to call a tool)
    """
        metadata_messages = messages + [
            answer_response,
            SystemMessage(content="""Given the conversation and the answer above, assess your confidence (0.0 to 1.0) "
            "and whether this requires human review before being shown to the user. "
            "If the user explicitly asked for human review, set requires_human_review to true.""")
        ]
        try:
            metadata = await structured_llm.ainvoke(metadata_messages)
            confidence = metadata.confidence
            requires_human_review = metadata.requires_human_review
        except GroqAPIError:
            logger.exception(
                "Groq confidence-metadata generation failed to parse for domain '%s'; "
                "defaulting to low confidence and forcing human review.", domain_name
            )
            confidence = 0.0
            requires_human_review = True

        final_answer = {
            "domain_name": domain_name,
            "answer": answer_response.content,
            "sources": sources,
            "confidence":confidence,
            "requires_human_review": requires_human_review

        }
        return {
            "messages":[answer_response],
            "final_answer": final_answer,
            "requires_human_review": requires_human_review,
            "tool_calls_remaining":remaining
        }

    graph.add_node("reason", reason)
    graph.set_entry_point("prepare_retrieval")
    graph.add_edge("prepare_retrieval","plan_retrieval")
    graph.add_conditional_edges("plan_retrieval",route_after_planning,
                                {
                                    "vector_retrieval":"retrieve",
                                    "sql_retrieval":"sql_retrieval",
                                    "none": "reason"
                                })
    graph.add_edge("retrieve", "grade_retrieval")
    graph.add_conditional_edges(
        "sql_retrieval",
        route_after_sql,
        {"reason": "reason", "insufficient_evidence": "insufficient_evidence"},
    )
    graph.add_conditional_edges(
        "grade_retrieval",
        route_after_grading,
        {
            "reason": "reason",
            "rewrite_query": "rewrite_query",
            "insufficient_evidence": "insufficient_evidence",
            "fallback_to_vector":"fallback_to_vector",
            "fallback_to_sql":"fallback_to_sql"
        },
    )
    graph.add_edge("fallback_to_sql","sql_retrieval")
    graph.add_edge("fallback_to_vector","retrieve")
    graph.add_edge("rewrite_query", "retrieve")
    graph.add_edge("insufficient_evidence", END)
    if tools:
        graph.add_node("tools", ToolNode(tools))
        graph.add_conditional_edges("reason",route_after_reason,{"tools":"tools", "reason":"reason", "end":END})
        graph.add_edge("tools","reason")

    else:
        graph.add_edge("reason",END)
    

    return graph.compile()
