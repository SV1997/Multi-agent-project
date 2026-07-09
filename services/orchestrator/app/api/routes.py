from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from ..core.security import verify_internal_secret
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), "../../../.."))
from shared.contracts.schema import OrchestratorRequest, AgentAnswer
from ..graph.supervisor import supervisor
from langchain_core.messages import HumanMessage
from datetime import datetime
import json
router = APIRouter()

async def event_generator(req:OrchestratorRequest):
    initital_state = {
        "messages":[HumanMessage(content=req.query)],
        "domain": None,
        "retrieved_context": [],
        "tool_calls_remaining":3,
        "requires_human_review": False,
        "final_answer": None
    }

    async for event in supervisor.astream_events(initital_state, version="v1"):
        if event["event"] == "on_chat_model_stream":
            chunk = event["data"]["chunk"]
            if chunk.content:
                yield f"data:{json.dumps({'token': chunk.content})}\n\n"
    
    yield "data:[DONE]\n\n"

@router.post("/query",
    response_model=AgentAnswer,
    dependencies=[Depends(verify_internal_secret)]
)
async def orchatrator_query(req:OrchestratorRequest):
    result = await supervisor.ainvoke({
        "messages":[HumanMessage(content=req.query)],
        "domain": None,
        "retrieved_context": [],
        "tool_calls_remaining":3,
        "requires_human_review": False,
        "final_answer": None
    })
    final_res={
        "domain": result["domain"],
        "answer": result["messages"][-1].content,
        "sources": [chunk.get("source", "unknown") for chunk in result["retrieved_context"]],
        "confidence":0.5,
        "requires_human_review": result["requires_human_review"],
        "generated_at": datetime.now()
    }
    return final_res


@router.post(
    "/query/stream",
    dependencies=[Depends(verify_internal_secret)]
)
async def stream_query(req:OrchestratorRequest):
    return StreamingResponse(
        event_generator(req),
        media_type="text/event-stream"
    )