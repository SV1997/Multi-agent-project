import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), "../../../.."))
from ..core.security import verify_internal_secret
from fastapi import APIRouter, Depends
from shared.contracts.schema import RetrievalQuery, RetrievalResponse

from ..pinecone.namespace_router import query_namespace

router = APIRouter()

@router.post("/query",
             response_model=RetrievalResponse,
             dependencies=[Depends(verify_internal_secret)])
async def query(req:RetrievalQuery):
    return await query_namespace(req)