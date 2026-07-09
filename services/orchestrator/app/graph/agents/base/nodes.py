import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), "../../../../.."))
from ....core.config import INTERNAL_SHARED_SECRET
import httpx
from langchain_core.messages import HumanMessage, SystemMessage
from ...state import AgentState
from dotenv import load_dotenv
async def retrieve_context(state:AgentState)-> dict:
    query = state["messages"][-1].content
    namespace= state["domain"]

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            "http://localhost:8001/api/v1/query",
            json={
                "query": query,
                "namespace": namespace,
                "top_k": 5
            },
            headers={"x-internal-secret": INTERNAL_SHARED_SECRET}
        )
        response.raise_for_status()
        data = response.json()

    return {"retrieved_context": data["results"]}

def build_context_prompt(state:AgentState)->str:
    context_parts=[]

    if not state.get("retrieved_context"):
        return "no relevant context found"
    
    for i, chunk in enumerate(state["retrieved_context"],1):
        source = chunk.get("source","unknown")
        content = chunk.get("content","")
        context_parts.append(f"[Source{i}: {source}]\n{content}")
    return "\n\n".join(context_parts)