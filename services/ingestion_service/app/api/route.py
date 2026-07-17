import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), "../../../.."))
from shared.contracts.schema import IngestionRequest, IngestionResponse
from fastapi import APIRouter, Depends, HTTPException
from ..core.security import verify_internal_secret
from ..loader.encoder import load_document
from ..pinecone.upsert import upsert_document
from ..chunking.splitter  import split_documents

router = APIRouter()

@router.post(
    "/ingest",
    dependencies=[Depends(verify_internal_secret)],
    response_model= IngestionResponse
)

async def ingest(req:IngestionRequest):
    try:
        all_chunks=[]

        for source in req.source:
            docs = load_document(
                source = source.path,
                source_type = source.type
            )

            chunk = split_documents(docs)
            all_chunks.extend(chunk)
        upserted = upsert_document(all_chunks, req.namespace)
        return IngestionResponse(
            chunks_created=upserted,
            namespace = req.namespace,
            status = "success"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Ingestion failed: {str(e)}"
        )