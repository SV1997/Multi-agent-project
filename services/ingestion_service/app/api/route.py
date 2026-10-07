import sys
import os
import pickle
from datetime import datetime, timezone
sys.path.append(os.path.join(os.path.dirname(__file__), "../../../.."))
from shared.contracts.schema import IngestionRequest, IngestionResponse
from fastapi import APIRouter, Depends, HTTPException
from ..core.security import verify_internal_secret
from ..loader.encoder import load_document
from ..pinecone.upsert import upsert_document
from ..chunking.splitter  import split_documents
from ..core.config import DATABASE_URL
import asyncpg
from rank_bm25 import BM25Okapi
async def get_connection():
    return await asyncpg.connect(DATABASE_URL)
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
        tokenized_corpus = [doc.page_content.lower().split() for doc in all_chunks]
        bm25Object = BM25Okapi(tokenized_corpus)
        upserted = upsert_document(all_chunks, req.namespace)
        saved_data={
            "Bm25": bm25Object,
            "chunks": [{"text":doc.page_content, "source":doc.metadata.get("source","")} for doc in all_chunks]
        }
        await save_bm25_index(req.namespace, saved_data)
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

async def save_bm25_index(namespace: str, saved_data):
    conn = await get_connection()
    try:
        index_data = pickle.dumps(saved_data)
        query = """
            INSERT INTO bm25_indexes (namespace, "indexData", "updatedAt")
            VALUES ($1, $2, $3)
            ON CONFLICT (namespace)
            DO UPDATE SET "indexData" = EXCLUDED."indexData", "updatedAt" = EXCLUDED."updatedAt"
        """
        await conn.execute(query, namespace, index_data, datetime.now(timezone.utc).replace(tzinfo=None))
    finally:
        await conn.close()
