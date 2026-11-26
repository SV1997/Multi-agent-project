import sys
import os
import asyncio
import pickle
import re
from urllib.parse import unquote, urlparse
from datetime import datetime, timezone
sys.path.append(os.path.join(os.path.dirname(__file__), "../../../.."))
from typing import Literal
from shared.contracts.schema import IngestionRequest, IngestionResponse
from fastapi import APIRouter, Depends, HTTPException, Path, Query
from ..core.security import verify_internal_secret
from ..loader.encoder import load_document, assess_chunking, assess_parse_quality, is_blank
from ..pinecone.upsert import upsert_document, doc_id_for_source
from ..pinecone.documents import list_documents, delete_document_chunks, chunks_without_document
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
                                       **bm25_tags(doc.metadata, taxonomy, req.namespace)})

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
    the chunks are then stored without categories and scripts/label_documents.py adds them later."""
    try:
        return load_taxonomy()
    except Exception as e:
        warnings.append(f"taxonomy unavailable ({type(e).__name__}); chunks were stored without categories - "
                        "fix the taxonomy and run scripts/label_documents.py --apply")
        return None

BM25_TAG_FIELDS = ("categories", "is_content", "file_name")

def bm25_tags(metadata: dict, taxonomy, namespace: str) -> dict:
    """The labels a chunk's keyword-index entry carries, taken from the metadata stored in Pinecone, so a
    filtered keyword search sees the same categories as a filtered vector search. The title is the
    taxonomy's (not the loader's), exactly what scripts/label_documents.py would write, so a labelling run
    after ingestion has nothing left to change."""
    tags = {key: metadata[key] for key in BM25_TAG_FIELDS if key in metadata}
    if taxonomy is not None:
        title = taxonomy.title_for(namespace, str(metadata.get("source", "")), metadata.get("file_name"))
        if title:
            tags["title"] = title
    return tags

def display_name(path: str) -> str:
    """Readable file name for messages: no query string, URL-decoded, gateway's upload UUID prefix removed."""
    name = unquote(path.split('?')[0].rsplit('/', 1)[-1])
    return re.sub(r"^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}-", "", name)

TEMP_FILE_NAME = re.compile(r"^tmp[0-9a-z_]{6,}\.\w+$", re.IGNORECASE)   # older uploads were stored under a temp file name

def document_name(source: str, title: str, doc_id: str) -> str:
    """Readable name for the documents list: the file name; the page/PDF title when the file name is a
    temp name or missing; the address for a bare web page; the document id as a last resort."""
    name = display_name(source) if source else ""
    if title and (not name or TEMP_FILE_NAME.match(name)):
        return title
    if not name and source.startswith(("http://", "https://")):
        parsed = urlparse(source)
        return f"{parsed.netloc}{parsed.path}".rstrip("/") or parsed.netloc
    return name or doc_id

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

async def delete_bm25_index(namespace: str):
    conn = await get_connection()
    try:
        await conn.execute('DELETE FROM bm25_indexes WHERE namespace=$1', namespace)
    finally:
        await conn.close()

async def delete_extractions(doc_id: str, namespace: str) -> int:
    """Remove the structured contract-extraction rows of a document. 0 if the table does not exist yet."""
    conn = await get_connection()
    try:
        status = await conn.execute('DELETE FROM doc_extractions WHERE doc_id = $1 AND namespace = $2', doc_id, namespace)
        return int(status.split()[-1])
    except asyncpg.UndefinedTableError:
        return 0
    finally:
        await conn.close()


Namespace = Literal["legal", "hr", "engineering", "finance", "support"]
DOC_ID_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"   # doc ids are hex hashes; this also keeps "#" and "/" out of the prefix search

@router.get("/documents", dependencies=[Depends(verify_internal_secret)])
async def list_indexed_documents(namespace: Namespace):
    """Every document currently in the namespace, with its chunk count and source."""
    try:
        docs = await asyncio.to_thread(list_documents, namespace)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not list documents: {e}")
    documents = [{**d, "name": document_name(d["source"], d.get("title", ""), d["doc_id"]), "file": display_name(d["source"]) if d["source"] else ""} for d in docs]
    documents.sort(key=lambda d: d["name"].lower())
    return {"namespace": namespace, "documents": documents}

@router.delete("/documents/{doc_id}", dependencies=[Depends(verify_internal_secret)])
async def delete_indexed_document(doc_id: str = Path(pattern=DOC_ID_PATTERN), namespace: Namespace = Query()):
    """Remove one document everywhere it is stored: Pinecone chunks, keyword index, contract extractions."""
    try:
        chunks_deleted = await asyncio.to_thread(delete_document_chunks, namespace, doc_id)

        keyword_chunks_removed = 0
        bm25_data = await load_bm25_index(namespace)
        if bm25_data:
            all_chunks = bm25_data["chunks"]
            kept = chunks_without_document(all_chunks, doc_id)
            keyword_chunks_removed = len(all_chunks) - len(kept)
            if keyword_chunks_removed:
                if kept:
                    tokenized_corpus = [c["text"].lower().split() for c in kept]
                    await save_bm25_index(namespace, {"Bm25": BM25Okapi(tokenized_corpus), "chunks": kept})
                else:
                    # an index over zero chunks cannot be built; retrieval treats "no row" as "no keyword index"
                    await delete_bm25_index(namespace)

        extractions_deleted = await delete_extractions(doc_id, namespace)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Deleting the document failed: {e}")

    if not (chunks_deleted or keyword_chunks_removed or extractions_deleted):
        raise HTTPException(status_code=404, detail=f"No document {doc_id} found in the {namespace} namespace")
    return {
        "doc_id": doc_id,
        "namespace": namespace,
        "chunks_deleted": chunks_deleted,
        "keyword_chunks_removed": keyword_chunks_removed,
        "extractions_deleted": extractions_deleted,
    }
