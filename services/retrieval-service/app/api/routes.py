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
)
from ..pinecone.namespace_router import query_namespace
import time
router = APIRouter()

@router.post("/query",
             response_model=RetrievalResponse,
             dependencies=[Depends(verify_internal_secret)])
async def query(req:RetrievalQuery):
    return await query_namespace(req)

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
    }
    handler = query_handlers.get(req.function)
    if handler is None:
        result = [{
            "source": "sql:error",
            "content": "No SQL query handler exists for the selected query name.",
        }]
    else:
        result = await handler(req)

    return {
        "results": result,
        "namespace": req.namespace,
        "query_time_ms": round((time.time() - start) * 1000, 2),
    }
