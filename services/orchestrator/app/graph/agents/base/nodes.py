import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), "../../../../../.."))
from ....core.config import INTERNAL_SHARED_SECRET, RETRIVAL_SERVICE_URL
import httpx
from langchain_core.messages import HumanMessage, SystemMessage
from ...state import AgentState
from dotenv import load_dotenv
async def retrieve_context(state:AgentState)-> dict:
    # search_query is set by the adaptive retrieval graph. Fall back to the
    # latest user question so this node remains usable on its own.
    query = state.get("search_query")
    if not query:
        human_messages = [message for message in state["messages"] if isinstance(message, HumanMessage)]
        query = human_messages[-1].content if human_messages else state["messages"][-1].content
    namespace= state["domain"]

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{RETRIVAL_SERVICE_URL}/api/v1/query",
            json={
                "query": query,
                "namespace": namespace,
                "top_k": 5
            },
            headers={"x-internal-secret": INTERNAL_SHARED_SECRET}
        )
        response.raise_for_status()
        data = response.json()

    return {
        "retrieved_context": data["results"],
        "retrieval_attempts": state.get("retrieval_attempts", 0) + 1,
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

def build_context_prompt(state:AgentState)->str:
    context_parts=[]

    if not state.get("retrieved_context"):
        return "no relevant context found"
    
    for i, chunk in enumerate(state["retrieved_context"],1):
        source = chunk.get("source","unknown")
        content = chunk.get("content","")
        context_parts.append(f"[Source{i}: {source}]\n{content}")
    return "\n\n".join(context_parts)
