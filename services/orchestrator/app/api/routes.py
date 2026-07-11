from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from ..core.security import verify_internal_secret
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), "../../../.."))
from shared.contracts.schema import OrchestratorRequest, AgentAnswer, PausedForReviewResponse, RequestResume
from ..graph.supervisor import supervisor
from langchain_core.messages import HumanMessage
from datetime import datetime
import json
from uuid import uuid4
from langgraph.types import Command
router = APIRouter()


async def event_generator(req:OrchestratorRequest):
    thread_id = str(uuid4())
    config = {"configurable":{"thread_id": thread_id}}
    initital_state = {
        "messages":[HumanMessage(content=req.query)],
        "domain": None,
        "retrieved_context": [],
        "tool_calls_remaining":3,
        "requires_human_reviews": False,
        "final_answer": None
    }

    async for event in supervisor.astream_events(initital_state, version="v1", config=config):
        if event["event"] == "on_chat_model_stream":
            chunk = event["data"]["chunk"]
            if chunk.content:
                yield f"data:{json.dumps({'token': chunk.content})}\n\n"
    
    state_snapshot = await supervisor.aget_state(config)

    if state_snapshot.interrupts:
        interrupt_data = state_snapshot.interrupts[0].value
        yield f"data:{json.dumps({'status':'paused_for_review', 'review_payload':interrupt_data, 'thread_id':thread_id})}\n\n"
    else:
        yield "data:[DONE]\n\n"

@router.post("/query",
    response_model=AgentAnswer | PausedForReviewResponse,
    dependencies=[Depends(verify_internal_secret)]
)
async def orchatrator_query(req:OrchestratorRequest):
    thread_id = str(uuid4())
    config = {"configurable":{"thread_id": thread_id}}
    result = await supervisor.ainvoke({
        "messages":[HumanMessage(content=req.query)],
        "domain": None,
        "retrieved_context": [],
        "tool_calls_remaining":3,
        "requires_human_reviews": False,
        "final_answer": None
    }, config=config)
    print(True if "__interrupt__" in result else None)
    if "__interrupt__" in result:
        return PausedForReviewResponse(
            review_payload=[interrupt.value for interrupt in result["__interrupt__"]],
            thread_id=thread_id
        )

    # print(result)
    final_res={
        "domain": result["domain"],
        "answer": result["messages"][-1].content,
        "sources": [chunk.get("source", "unknown") for chunk in result["retrieved_context"]],
        "confidence":0.5,
        "requires_human_review": result["requires_human_reviews"],
        "generated_at": datetime.now()
    }
    return final_res

@router.post(
    "/query/resume",
    dependencies=[Depends(verify_internal_secret)],
    response_model=AgentAnswer | PausedForReviewResponse
)
async def resume_query(req: RequestResume):
    config = {"configurable": {"thread_id": req.thread_id}}
    result = await supervisor.ainvoke(
        Command(resume=req.human_response.model_dump()),
        config=config
    )
    return {
        "domain": result["domain"],
        "answer": result["final_answer"]["answer"], 
        "sources": [chunk.get("source", "unknown") for chunk in result["retrieved_context"]],
        "confidence": result["final_answer"]["confidence"],
        "requires_human_review": result["requires_human_reviews"],
        "generated_at": datetime.now()
    }

@router.post(
    "/query/stream",
    dependencies=[Depends(verify_internal_secret)]
)
async def stream_query(req:OrchestratorRequest):
    return StreamingResponse(
        event_generator(req),
        media_type="text/event-stream"
    )