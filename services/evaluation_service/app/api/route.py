import sys
import os
import asyncio
sys.path.append(os.path.join(os.path.dirname(__file__), "../../../.."))
from shared.contracts.schema import EvalRequest, EvalResponse
from fastapi import APIRouter, Depends, HTTPException
from ..core.security import verify_internal_secret
from ragas_eval.evaluator import evaluate_single
router =APIRouter()

@router.post("/evaluate",
             dependencies=[Depends(verify_internal_secret)],
             response_model=EvalResponse)
async def evaluate(req:EvalRequest):
    # evaluate_single calls ragas.evaluate(), which runs its own asyncio.run()
    # internally - that can't nest inside uvicorn's already-running event loop,
    # so it has to execute in a separate thread with no loop of its own.
    return await asyncio.to_thread(
        evaluate_single, req.query, req.answer, req.retrieved_context, req.confidence
    )