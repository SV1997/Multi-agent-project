import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), "../../../../../.."))
from ....core import config
from ....core.config import INTERNAL_SHARED_SECRET, RETRIVAL_SERVICE_URL
import logging
import httpx
from langchain_core.messages import HumanMessage, SystemMessage
from ...state import AgentState
from dotenv import load_dotenv

logger = logging.getLogger(__name__)


async def retrieve_context(state:AgentState)-> dict:
    # search_query is set by the adaptive retrieval graph. Fall back to the
    # latest user question so this node remains usable on its own.
    query = state.get("search_query")
    if not query:
        human_messages = [message for message in state["messages"] if isinstance(message, HumanMessage)]
        query = human_messages[-1].content if human_messages else state["messages"][-1].content
    namespace= state["domain"]

    payload = {
        "query": query,
        "namespace": namespace,
        "top_k": 5
    }
    # Categories narrow the search to one part of the domain (localized search). Without any, the request is
    # exactly what it always was. When the frame step left a search plan, each new search in the same question
    # follows it one level wider (own categories -> the parents' families -> the whole domain), and the level is
    # recorded so it is known which level the evidence came from.
    levels = state.get("localize_levels")
    trace = {}
    if levels:
        call_number = state.get("retrieval_calls", 0)
        step = levels[min(call_number, len(levels) - 1)]
        categories = step["categories"]
        trace = {
            "retrieval_calls": call_number + 1,
            "fallback_level": step["level"],
            "levels_tried": list(state.get("levels_tried") or []) + [step["level"]],
        }
        logger.info("Search %d of this question: level %d, categories %s", call_number + 1, step["level"],
                    categories if categories else "the whole domain")
    else:
        categories = state.get("localize_categories")
    if categories:
        payload["categories"] = categories

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{RETRIVAL_SERVICE_URL}/api/v1/query",
            json=payload,
            headers={"x-internal-secret": INTERNAL_SHARED_SECRET}
        )
        response.raise_for_status()
        data = response.json()
        print(data)
    return {
        "retrieved_context": data["results"],
        "retrieval_attempts": state.get("retrieval_attempts", 0) + 1,
        **trace,
    }

async def retrieve_sql_context(state:AgentState, function:str, extracted_data:dict)->dict:
        query = state.get("search_query")
        print(f"retrieve_sql_context: function={function!r} search_query={query!r}")
        if not query:
                human_messages = [message for message in state["messages"] if isinstance(message, HumanMessage)]
                query = human_messages[-1].content if human_messages else state["messages"][-1].content
        async with httpx.AsyncClient(timeout=30.0) as client:
             response = await client.post(
                         f"{RETRIVAL_SERVICE_URL}/api/v1/sql_query",
                         json={
                             "query": query,
                             "function":function,
                             "employee_email": state.get("employee_email"),
                             "namespace": state.get("domain"),
                             "data":extracted_data

                         },
                         headers={"x-internal-secret": INTERNAL_SHARED_SECRET}
                     )
             response.raise_for_status()
             data = response.json()
             print(data["results"])
             return {
                     "retrieved_context": data["results"],
                 }

def edge_order(items: list) -> list:
    """Best items at both ends (ranks 1,3,5,4,2), since long prompts lose the middle."""
    return items[0::2] + items[1::2][::-1]

def build_context_prompt(state:AgentState)->str:
    context_parts=[]

    if not state.get("retrieved_context"):
        return "no relevant context found"
    
    numbered = list(enumerate(state["retrieved_context"],1))  # numbers keep the retrieval rank
    if config.CONTEXT_REORDER:
        numbered = edge_order(numbered)
    for i, chunk in numbered:
        source = chunk.get("source","unknown")
        content = chunk.get("content","")
        context_parts.append(f"[Source{i}: {source}]\n{content}")
    return "\n\n".join(context_parts)
