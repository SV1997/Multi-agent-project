from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from ..core.security import verify_internal_secret
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), "../../../.."))
from shared.contracts.schema import OrchestratorRequest, AgentAnswer, PausedForReviewResponse, RequestResume
# from ..graph.supervisor import supervisor
from langchain_core.messages import HumanMessage
from datetime import datetime
import json
from uuid import uuid4
from langgraph.types import Command
from ..main import app_state
router = APIRouter()

SUPERVISOR_KEY = "supervisor"

async def event_generator(req:OrchestratorRequest):
    thread_id = str(uuid4())
    supervisor = app_state[SUPERVISOR_KEY]
    config = {"configurable":{"thread_id": thread_id}}
    initial_state = {
        "messages":[HumanMessage(content=req.query)],
        "domain": None,
        "retrieved_context": [],
        "tool_calls_remaining":3,
        "requires_human_review": False,
        "final_answer": None,
        "allowed_namespace": req.allowed_namespace
    }
    steps_list = ["classify_domain","check_authorization","legal_agent","hr_agent","support_agent","coding_agent","engineering_agent", "retrieve",]
    seen_stages = set()
    
    async for event in supervisor.astream_events(initial_state, version="v2", config=config, subgraphs=True):
        # print(event['event'])
        if event["event"] == "on_chain_start":
            node_name = event.get("name")
            if node_name in steps_list and node_name not in seen_stages:
                seen_stages.add(node_name)
                yield f"data:{json.dumps({'node_name': node_name})}\n\n"

        if event["event"] == "on_custom_event":   # verify this exact name for your version
            custom_data = event.get("data", {})
            print(custom_data)
            if "tool_call" in custom_data:
                yield f"data:{json.dumps({'tool_call': custom_data['tool_call']})}\n\n"

        if event["event"] == "on_chat_model_stream":
            tags = event.get("tags", [])
            if "final-answer" in tags:
                chunk = event["data"]["chunk"]
                if chunk.content:
                    yield f"data:{json.dumps({'token': chunk.content})}\n\n"
        
    state_snapshot = await supervisor.aget_state(config)
    if state_snapshot.interrupts:
        interrupt_data = state_snapshot.interrupts[0].value
        yield f"data:{json.dumps({'status':'paused_for_review', 'review_payload':interrupt_data, 'thread_id':thread_id})}\n\n"
    else:
        if state_snapshot.values.get("authorization_denied"):
            denial_text = state_snapshot.values["messages"][-1].content
            yield f"data:{json.dumps({'token': denial_text})}\n\n"
        yield "data:[DONE]\n\n"

async def event_generator_resume(req:RequestResume):
    config = {"configurable":{"thread_id": req.thread_id}}
    supervisor = app_state[SUPERVISOR_KEY]

    async for event in supervisor.astream_events(Command(resume=req.human_response.model_dump()),version="v1", config=config):
        if event["event"] == "on_chat_model_stream":
            chunk = event["data"]["chunk"]
            if chunk.content:
                yield f"data:{json.dumps({'token': chunk.content, 'requires_human_review': False})}\n\n"

    state_snapshot = await supervisor.aget_state(config)
    if state_snapshot.interrupts:
        interrupt_data = state_snapshot.interrupts[0].value
        yield f"data:{json.dumps({'status':'paused_for_review', 'review_payload':interrupt_data, 'thread_id':req.thread_id})}\n\n"
    else:
        final_answer = (state_snapshot.values or {}).get("final_answer") or {}
        answer_text = final_answer.get("answer")
        if answer_text:
            yield f"data:{json.dumps({'token': answer_text, 'requires_human_review': False})}\n\n"
        yield "data:[DONE]\n\n"

@router.post("/query",
    response_model=AgentAnswer | PausedForReviewResponse,
    dependencies=[Depends(verify_internal_secret)]
)
async def orchatrator_query(req:OrchestratorRequest):
    thread_id = str(uuid4())
    config = {"configurable":{"thread_id": thread_id}}
    supervisor = app_state[SUPERVISOR_KEY]
    result = await supervisor.ainvoke({
        "messages":[HumanMessage(content=req.query)],
        "domain": None,
        "retrieved_context": [],
        "tool_calls_remaining":3,
        "requires_human_review": False,
        "final_answer": None,
        "allowed_namespace": req.allowed_namespace
    }, config=config)
    if "__interrupt__" in result:
        print(True if "__interrupt__" in result else None)
        return {
            "review_payload":[interrupt.value for interrupt in result["__interrupt__"]],
            "thread_id":thread_id
        }

    # print(result, "67")
    final_res={
        "domain": result["domain"],
        "answer": result["messages"][-1].content,
        "sources": [chunk.get("source", "unknown") for chunk in result["retrieved_context"]],
        "confidence":result["final_answer"]["confidence"],
        "requires_human_review": result["requires_human_review"],
        "generated_at": datetime.now()
    }
    return final_res

@router.post(
    "/query/resume",
    dependencies=[Depends(verify_internal_secret)],
    response_model=AgentAnswer | PausedForReviewResponse
)
async def resume_query(req: RequestResume):
    print(req)
    config = {"configurable": {"thread_id": req.thread_id}}
    supervisor = app_state[SUPERVISOR_KEY]
    result = await supervisor.ainvoke(
        Command(resume=req.human_response.model_dump()),
        config=config
    )
    return {
        "domain": result["domain"],
        "answer": result["final_answer"]["answer"], 
        "sources": [chunk.get("source", "unknown") for chunk in result["retrieved_context"]],
        "confidence": result["final_answer"]["confidence"],
        "requires_human_review": result["requires_human_review"],
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

@router.post(
    "/query/stream/resume",
    dependencies=[Depends(verify_internal_secret)]
)
async def stream_query_resume(req:RequestResume):
    return StreamingResponse(
        event_generator_resume(req),
        media_type="text/event-stream"
    )