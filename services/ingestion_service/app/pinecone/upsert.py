from langchain_pinecone import PineconeVectorStore
from pinecone import Pinecone
import hashlib
import os
import sys
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse
sys.path.append(os.path.join(os.path.dirname(__file__), "../../../.."))
from shared.embeddings.embeddings import embeddings
from langchain_core.documents import Document
from ..core.config import PINECONE_API_KEY, PINECONE_INDEX_NAME


def doc_id_for_source(path: str) -> str:
    """Stable id for a source. Query strings are dropped so a re-signed
    SeaweedFS URL for the same object keeps the same doc_id."""
    parsed = urlparse(path)
    stable = f"{parsed.netloc}{parsed.path}" if parsed.scheme in ("http", "https") else path
    return hashlib.sha1(stable.encode("utf-8")).hexdigest()[:16]


def make_chunk_id(doc_id: str, chunk_text: str) -> str:
    return f"{doc_id}#{hashlib.sha1(chunk_text.encode('utf-8')).hexdigest()[:12]}"


def _get_index():
    return Pinecone(api_key=PINECONE_API_KEY).Index(PINECONE_INDEX_NAME)


def _existing_ids(index, namespace: str, doc_id: str) -> list[str]:
    # Serverless indexes cannot delete by metadata filter, but can list by ID prefix.
    ids: list[str] = []
    for page in index.list(prefix=f"{doc_id}#", namespace=namespace):
        ids.extend(page)
    return ids


def upsert_document(
        documents: list[Document],
        namespace: str,
        doc_id: Optional[str] = None,
        effective_date: Optional[str] = None,
) -> int:
    """Upsert chunks of ONE document with deterministic IDs and remove its stale chunks.

    Returns the number of unique chunks the document now has in the index.
    """
    if doc_id is None:
        doc_id = doc_id_for_source(documents[0].metadata.get("source", "")) if documents else ""
    index = _get_index()
    old_ids = _existing_ids(index, namespace, doc_id) if doc_id else []

    version = 1
    if old_ids:
        old = index.fetch(ids=old_ids[:1], namespace=namespace).vectors.get(old_ids[0])
        version = int((old.metadata or {}).get("version", 0)) + 1 if old else 1
    ingested_at = datetime.now(timezone.utc).isoformat()

    unique: dict[str, Document] = {}
    for doc in documents:
        doc.metadata.update({"doc_id": doc_id, "version": version, "ingested_at": ingested_at})
        if effective_date:  # Pinecone metadata rejects null values
            doc.metadata["effective_date"] = effective_date
        unique.setdefault(make_chunk_id(doc_id, doc.page_content), doc)

    if unique:
        PineconeVectorStore.from_documents(
            documents=list(unique.values()),
            ids=list(unique.keys()),
            embedding=embeddings,
            index_name=PINECONE_INDEX_NAME,
            namespace=namespace
        )
    # Delete only after the new chunks are in, so the document is never empty mid-ingest.
    stale = [i for i in old_ids if i not in unique]
    for start in range(0, len(stale), 1000):
        index.delete(ids=stale[start:start + 1000], namespace=namespace)
    return len(unique)
