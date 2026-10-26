"""List and delete whole documents in one namespace.

Two kinds of chunks exist in the index:

* current chunks have the id "<doc_id>#<hash>" (see upsert.make_chunk_id), so the document is in the id
  and a document is deleted by deleting every id with its prefix;
* older chunks have random ids and no doc_id. Their only link to a document is the `source` metadata, so
  they are grouped by source under a synthetic id "src-<hash of the source>".
"""
import hashlib
from typing import Optional

from .upsert import _get_index, _existing_ids

FETCH_BATCH = 100     # ids per fetch request
DELETE_BATCH = 1000   # Pinecone's limit on ids per delete request
LEGACY_PREFIX = "src-"


def legacy_key(source: str) -> str:
    return LEGACY_PREFIX + hashlib.sha1(source.encode("utf-8")).hexdigest()[:16]


def document_key(chunk_id: str, metadata: dict) -> str:
    """The document a chunk belongs to."""
    if "#" in chunk_id:
        return chunk_id.split("#")[0]
    source = str(metadata.get("source") or "")
    return legacy_key(source) if source else chunk_id    # no source at all: the chunk stands alone


def _as_int(value) -> Optional[int]:
    # Pinecone stores every number as a float (2 comes back as 2.0)
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _all_ids(index, namespace: str) -> list[str]:
    return [chunk_id for page in index.list(namespace=namespace) for chunk_id in page]


def _fetch_metadata(index, namespace: str, ids: list[str]) -> dict[str, dict]:
    """chunk id -> metadata, fetched FETCH_BATCH ids at a time."""
    found: dict[str, dict] = {}
    for start in range(0, len(ids), FETCH_BATCH):
        batch = ids[start:start + FETCH_BATCH]
        vectors = index.fetch(ids=batch, namespace=namespace).vectors
        for chunk_id in batch:
            vector = vectors.get(chunk_id)
            found[chunk_id] = dict(vector.metadata or {}) if vector else {}
    return found


def _legacy_chunks(index, namespace: str) -> dict[str, dict]:
    """chunk id -> metadata for every chunk without a "#" in its id."""
    return _fetch_metadata(index, namespace, [i for i in _all_ids(index, namespace) if "#" not in i])


def list_documents(namespace: str, index=None) -> list[dict]:
    """One entry per document: {doc_id, chunks, source, title, version, ingested_at}.

    Current chunks are counted from their ids, with ONE chunk per document fetched for its metadata.
    Older chunks have to be fetched all (their ids say nothing), then grouped by source.
    """
    index = index or _get_index()
    ids = _all_ids(index, namespace)

    chunk_counts: dict[str, int] = {}
    metadata: dict[str, dict] = {}

    current_sample: dict[str, str] = {}
    for chunk_id in ids:
        if "#" in chunk_id:
            key = document_key(chunk_id, {})
            chunk_counts[key] = chunk_counts.get(key, 0) + 1
            current_sample.setdefault(key, chunk_id)
    for chunk_id, meta in _fetch_metadata(index, namespace, list(current_sample.values())).items():
        metadata[document_key(chunk_id, meta)] = meta

    for chunk_id, meta in _fetch_metadata(index, namespace, [i for i in ids if "#" not in i]).items():
        key = document_key(chunk_id, meta)
        chunk_counts[key] = chunk_counts.get(key, 0) + 1
        metadata.setdefault(key, meta)

    return [
        {
            "doc_id": key,
            "chunks": count,
            "source": str(metadata.get(key, {}).get("source", "")),
            "title": str(metadata.get(key, {}).get("title", "") or ""),
            "version": _as_int(metadata.get(key, {}).get("version")),
            "ingested_at": metadata.get(key, {}).get("ingested_at"),
        }
        for key, count in chunk_counts.items()
    ]


def chunk_ids_of_document(namespace: str, doc_id: str, index) -> list[str]:
    """Every chunk id belonging to the document."""
    if doc_id.startswith(LEGACY_PREFIX):
        return [chunk_id for chunk_id, meta in _legacy_chunks(index, namespace).items()
                if document_key(chunk_id, meta) == doc_id]
    ids = _existing_ids(index, namespace, doc_id)
    if not ids and index.fetch(ids=[doc_id], namespace=namespace).vectors:
        return [doc_id]        # an older chunk that had no source, so its own id is its document id
    return ids


def delete_document_chunks(namespace: str, doc_id: str, index=None) -> int:
    """Delete every chunk of one document from Pinecone. Returns how many chunks were deleted."""
    index = index or _get_index()
    ids = chunk_ids_of_document(namespace, doc_id, index)
    for start in range(0, len(ids), DELETE_BATCH):
        index.delete(ids=ids[start:start + DELETE_BATCH], namespace=namespace)
    return len(ids)


def _keyword_chunk_key(chunk: dict) -> str:
    if chunk.get("doc_id"):
        return str(chunk["doc_id"])
    source = str(chunk.get("source") or "")
    return legacy_key(source) if source and source != "unknown" else ""


def chunks_without_document(chunks: list, doc_id: str) -> list[dict]:
    """The keyword-index chunks left after removing one document.

    Chunks are matched the same way as in Pinecone: by doc_id, or for older chunks by source.
    Indexes saved by even older versions hold plain strings; those are wrapped (as ingestion does) and
    kept, because nothing links them to any document.
    """
    wrapped = [c if isinstance(c, dict) else {"text": c, "source": "unknown"} for c in chunks]
    return [c for c in wrapped if _keyword_chunk_key(c) != doc_id]
