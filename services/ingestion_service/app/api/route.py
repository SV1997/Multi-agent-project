import sys
import os
import pickle
from datetime import datetime, timezone
sys.path.append(os.path.join(os.path.dirname(__file__), "../../../.."))
from shared.contracts.schema import IngestionRequest, IngestionResponse
from fastapi import APIRouter, Depends, HTTPException
from ..core.security import verify_internal_secret
from ..loader.encoder import load_document, assess_parse_quality
from ..pinecone.upsert import upsert_document, doc_id_for_source
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
        upserted = 0
        new_chunks = []
        doc_ids = set()
        warnings: list[str] = []

        for source in req.source:

            docs = load_document(
                source = source.path,
                source_type = source.type
            )

            warnings.extend(f"{source.path.split('?')[0]}: {w}" for w in assess_parse_quality(docs, source.type))
            chunk = split_documents(docs)
            doc_id = source.doc_id or doc_id_for_source(source.path)
            upserted += upsert_document(chunk, req.namespace, doc_id, source.effective_date)
            doc_ids.add(doc_id)
            seen_texts = set()
            for doc in chunk:
                if doc.page_content not in seen_texts:
                    seen_texts.add(doc.page_content)
                    new_chunks.append({"text":doc.page_content, "source":doc.metadata.get("source",""), "doc_id":doc_id})

        existing_data = await load_bm25_index(req.namespace)
        existing_chunks = existing_data["chunks"] if existing_data else []
        # drop the previous version of any re-ingested document before adding the new one
        existing_chunks = [c for c in existing_chunks if c.get("doc_id") not in doc_ids]
        combined_chunks = existing_chunks + new_chunks

        tokenized_corpus = [c["text"].lower().split() for c in combined_chunks]
        bm25Object = BM25Okapi(tokenized_corpus)
        saved_data={
            "Bm25": bm25Object,
            "chunks": combined_chunks
        }
        await save_bm25_index(req.namespace, saved_data)
        return IngestionResponse(
            chunks_created=upserted,
            namespace = req.namespace,
            status = "success",
            warnings = warnings
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Ingestion failed: {str(e)}"
        )

async def load_bm25_index(namespace: str):
    conn = await get_connection()
    try:
        row = await conn.fetchrow('SELECT "indexData" FROM bm25_indexes WHERE namespace=$1', namespace)
        if row is None:
            return None
        return pickle.loads(row["indexData"])
    finally:
        await conn.close()

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
