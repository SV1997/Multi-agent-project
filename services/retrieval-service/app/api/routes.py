import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), "../../../.."))
from ..core.security import verify_internal_secret
from fastapi import APIRouter, Depends
from shared.contracts.schema import RetrievalQuery, RetrievalResponse, SQLRetrievalResponse, SQLRetrievalRequest
from ..sql.sql_queries import (
    CTC_data,
    contract_tracking,
    deployment_status,
    get_ticket_status,
    leave_balance,
    claim_tracking
)
from ..sql.aggregate_queries import claims_by_status_for_team, leave_taken_by_month
from ..pinecone.namespace_router import query_namespace
import time
import logging
router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/query",
             response_model=RetrievalResponse,
             dependencies=[Depends(verify_internal_secret)])
async def query(req:RetrievalQuery):
    try:
        return await query_namespace(req)
    except Exception:
        logger.exception("query_namespace failed for namespace '%s'.", req.namespace)
        return {
            "results": [{"source": "error", "content": "Retrieval failed due to an internal error.", "score": 0.0, "metadata":{}}],
            "namespace": req.namespace,
            "query_time_ms": 0.0,
        }

@router.post("/sql_query",
             response_model=SQLRetrievalResponse,
             dependencies=[Depends(verify_internal_secret)])
async def sql_query(req:SQLRetrievalRequest):
    start = time.time()
    query_handlers = {
        "leave_balance": leave_balance,
        "CTC_data": CTC_data,
        "get_ticket_status": get_ticket_status,
        "contract_tracking": contract_tracking,
        "deployment_status": deployment_status,
        "claim_tracking": claim_tracking,
        "claims_by_status_for_team": claims_by_status_for_team,
        "leave_taken_by_month": leave_taken_by_month,
    }
    handler = query_handlers.get(req.function)
    if handler is None:
        result = [{
            "source": "sql:error",
            "content": "No SQL query handler exists for the selected query name.",
        }]
    else:
        try:
            result = await handler(req)
        except Exception:
            logger.exception("SQL handler '%s' failed for namespace '%s'.", req.function, req.namespace)
            result = [{"source": "sql:error", "content": "The lookup failed due to an internal error."}]

    return {
        "results": result,
        "namespace": req.namespace,
        "query_time_ms": round((time.time() - start) * 1000, 2),
    }
