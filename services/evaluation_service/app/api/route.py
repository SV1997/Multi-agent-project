import sys
import os
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
    return evaluate_single(req.query, req.answer, req.retrieved_context, req.confidence)