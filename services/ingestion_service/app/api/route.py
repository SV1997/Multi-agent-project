import sys
import os
import asyncio
import pickle
import re
from urllib.parse import unquote
from datetime import datetime, timezone
sys.path.append(os.path.join(os.path.dirname(__file__), "../../../.."))
from shared.contracts.schema import IngestionRequest, IngestionResponse
from fastapi import APIRouter, Depends, HTTPException
from ..core.security import verify_internal_secret
from ..loader.encoder import load_document, assess_chunking, assess_parse_quality, is_blank
from ..pinecone.upsert import upsert_document, doc_id_for_source
from ..chunking.splitter  import split_documents
from ..extraction.contracts import document_text, extract_contract, save_extraction
from ..core.config import CONTRACT_EXTRACTION_ENABLED, DATABASE_URL
from shared.taxonomy.taxonomy import load_taxonomy
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
        empty_sources = 0
        taxonomy = load_taxonomy_or_warn(warnings)

        for source in req.source:

            docs = load_document(
                source = source.path,
                source_type = source.type
            )

            warnings.extend(f"{display_name(source.path)}: {w}" for w in assess_parse_quality(docs, source.type))
            chunk = split_documents(docs)
            if not chunk or is_blank(docs):
                warnings.append(f"{display_name(source.path)}: no extractable text - nothing was indexed")
                empty_sources += 1
                continue
            warnings.extend(f"{display_name(source.path)}: {w}" for w in assess_chunking(docs, chunk, source.type))
            doc_id = source.doc_id or doc_id_for_source(source.path)
            if source.file_name:
                for piece in chunk:
                    piece.metadata["file_name"] = source.file_name
            upserted += upsert_document(chunk, req.namespace, doc_id, source.effective_date, taxonomy=taxonomy)
            doc_ids.add(doc_id)
            if CONTRACT_EXTRACTION_ENABLED and req.namespace == "legal" and source.document_type == "contract":
                warnings.extend(await extract_and_store(docs, doc_id, chunk[0].metadata.get("version", 1), source.path))
            seen_texts = set()
            for doc in chunk:
                if doc.page_content not in seen_texts:
                    seen_texts.add(doc.page_content)
                    new_chunks.append({"text":doc.page_content, "source":doc.metadata.get("source",""), "doc_id":doc_id,
                                       **bm25_tags(doc.metadata)})

        if empty_sources == len(req.source):
            names = ", ".join(display_name(s.path) for s in req.source)
            raise HTTPException(status_code=422, detail=(
                f"No text could be extracted from {names}; nothing was indexed. "
                "The file may be blank or scanned (OCR is not applied)."))

        existing_data = await load_bm25_index(req.namespace)
        existing_chunks = existing_data["chunks"] if existing_data else []
        # drop the previous version of any re-ingested document before adding the new one
        # indexes saved by older versions hold plain strings; wrap them so they can be filtered and re-tokenised
        existing_chunks = [c if isinstance(c, dict) else {"text": c, "source": "unknown"} for c in existing_chunks]
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
            status = "partial" if empty_sources else "success",
            warnings = warnings
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Ingestion failed: {str(e)}"
        )

def load_taxonomy_or_warn(warnings: list[str]):
    """The taxonomy, or None with a warning. A broken taxonomy file must not stop documents being ingested;
    the chunks are then stored without categories and scripts/backfill.py adds them later."""
    try:
        return load_taxonomy()
    except Exception as e:
        warnings.append(f"taxonomy unavailable ({type(e).__name__}); chunks were stored without categories - "
                        "fix the taxonomy and run scripts/backfill.py --apply")
        return None

BM25_TAG_FIELDS = ("categories", "is_content", "file_name")

def bm25_tags(metadata: dict) -> dict:
    """The labels a chunk's keyword-index entry carries, taken from the metadata stored in Pinecone, so a
    filtered keyword search sees the same categories as a filtered vector search."""
    return {key: metadata[key] for key in BM25_TAG_FIELDS if key in metadata}

def display_name(path: str) -> str:
    """Readable file name for messages: no query string, URL-decoded, gateway's upload UUID prefix removed."""
    name = unquote(path.split('?')[0].rsplit('/', 1)[-1])
    return re.sub(r"^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}-", "", name)

async def extract_and_store(docs, doc_id: str, version: int, path: str) -> list[str]:
    """Structured contract extraction. Never fails the ingestion; problems come back as warnings."""
    label = display_name(path)
    try:
        text = document_text(docs)
        extraction = await asyncio.to_thread(extract_contract, text)
        conn = await get_connection()
        try:
            await save_extraction(conn, doc_id, int(version), "legal", label, extraction, "contract")
        finally:
            await conn.close()
        return [f"{label}: extraction needs review - {r}" for r in extraction.review_reasons]
    except Exception as e:
        return [f"{label}: contract extraction failed - {e}"]

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
