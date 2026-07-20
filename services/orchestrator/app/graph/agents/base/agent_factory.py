from langgraph.graph import StateGraph, START, END
from ...state import AgentState
from langgraph.prebuilt import ToolNode
from langchain.messages import HumanMessage, SystemMessage, AIMessage
from .nodes import retrieve_context, build_context_prompt
import sys
import os
from langchain_core.callbacks import adispatch_custom_event
sys.path.append(os.path.join(os.path.dirname(__file__), "../../../.."))
from shared.contracts.schema import AgentAnswer, AgentAnswerLLM

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



def build_domain_agent(llm,system_prompt:str, tools: list = None, domain_name: str = ""):
    tool = tools or []
    graph = StateGraph(AgentState)
    graph.add_node("retrieve", retrieve_context)
    structured_llm = llm.with_structured_output(AgentAnswerLLM, method="json_schema", strict=True).with_config(tags=["metadata-only"])
    llm_with_tools = (llm.bind_tools(tools) if tool else llm).with_config(tags=["tool-decision"])
    plain_llm = llm.with_config(tags=["final-answer"])

    async def reason(state:AgentState)-> dict:

        context = build_context_prompt(state)
        remaining = state["tool_calls_remaining"]

        messages = [
            SystemMessage(content=(
                f"{system_prompt}\n\n"
                "When you call a tool, report exactly what the tool returns. "
                "Never invent specific facts (numbers, dates, names, statuses) "
                "that are not present in the tool output or the retrieved "
                "context below. If a tool result indicates the data isn't "
                "available (e.g. not implemented, empty, or an error), say so "
                "plainly instead of guessing an answer.\n\n"
                f"Context:{context}"
            ))
            ] + state["messages"]

        # Once out of tool calls, force a final natural-language answer
        # instead of letting the model emit another (unexecuted) tool call.
        sources = [chunk.get("sources", "unknown") for chunk in state.get("retrieved_context") or []]
        if remaining<=0:
            answer = await plain_llm.ainvoke(messages)
            return await _finalize_answer(answer, messages, domain_name, sources, remaining)

        res = await llm_with_tools.ainvoke(messages)
        if res.tool_calls:
            tool_names = [tc["name"] for tc in res.tool_calls]
            await adispatch_custom_event("tool_call", {"tool_call": tool_names})
            return {"messages":[res], "tool_calls_remaining":remaining-1}

            


        answer_response = await plain_llm.ainvoke(messages)

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
        metadata = await structured_llm.ainvoke(metadata_messages)

        final_answer = {
            "domain_name": domain_name,
            "answer": answer_response.content,
            "sources": sources,
            "confidence":metadata.confidence,
            "requires_human_review": metadata.requires_human_review

        }
        return {
            "messages":[answer_response],
            "final_answer": final_answer,
            "requires_human_review": metadata.requires_human_review,
            "tool_calls_remaining":remaining
        }

    graph.add_node("reason", reason)
    graph.set_entry_point("retrieve")
    graph.add_edge("retrieve", "reason")
    if tools:
        graph.add_node("tools", ToolNode(tools))
        graph.add_conditional_edges("reason",route_after_reason,{"tools":"tools", "reason":"reason", "end":END})
        graph.add_edge("tools","reason")

    else:
        graph.add_edge("reason",END)
    

    return graph.compile()


