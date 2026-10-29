import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), "../../../.."))
import time
from langchain_pinecone import PineconeVectorStore
from shared.embeddings.embeddings import embeddings
from shared.contracts.schema import RetrievalQuery, RetrievalResponse, RetrievedChunk
from ..core import config as cfg
from ..core.config import PINECONE_INDEX_NAME
from .reranker import rerank
from .filters import pinecone_filter, keyword_chunk_allowed, chunk_tags, LOCALIZED_NAMESPACES
import asyncio
import logging
from ..storage.bm25score import load_bm25

logger = logging.getLogger(__name__)

def search(vector_store, bm25_data, req: RetrievalQuery, candidates: int, categories, localize: bool) -> list[RetrievedChunk]:
    """The filtered search and the fallback must run the identical search, so it is one function."""
    if localize:
        results = vector_store.similarity_search_with_score(
            query= req.query,
            k=candidates,
            filter=pinecone_filter(categories)
        )
    else:
        results = vector_store.similarity_search_with_score(
            query= req.query,
            k=candidates
        )

    rrf_score ={}

    meta_lookup = {}

    k=60 

    for rank,(doc,score) in enumerate(results, start=1):
        rrf_score[doc.page_content] = rrf_score.get(doc.page_content,0)+(1/(k+rank))
        meta_lookup[doc.page_content] = doc.metadata

    if bm25_data is not None:
        bm25_scores = bm25_data["Bm25"].get_scores(req.query.lower().split())
        bm25_chunks = bm25_data["chunks"]

        bm25_ranked = sorted(
            zip(bm25_chunks, bm25_scores), key=lambda x: x[1], reverse=True
        )
        if localize:
            # scored as always, then reduced; ranks are counted after this so they stay 1, 2, 3...
            bm25_ranked = [(chunk, score) for chunk, score in bm25_ranked if keyword_chunk_allowed(chunk, categories)]
        for rank, (chunk, _) in enumerate(bm25_ranked, start=1):
            if isinstance(chunk, dict):
                text = chunk["text"]
                source = chunk.get("source", "unknown")
            else:
                text = chunk
                source = "unknown"
            rrf_score[text] = rrf_score.get(text, 0) + 1 / (k + rank)
            if text not in meta_lookup:
                meta_lookup[text] = {"source": source, **(chunk_tags(chunk) if localize else {})}

    chunks = [
        RetrievedChunk(
            content = text,
            score= float(score),
            source = meta_lookup.get(text, {}).get("source", "unknown"),
            metadata = meta_lookup.get(text, {})
        ) for text, score in rrf_score.items()
    ]
    chunks.sort(key=lambda c: c.score, reverse=True)
    chunks = chunks[:candidates]
    return chunks


async def query_namespace(req: RetrievalQuery) -> RetrievalResponse:
    start = time.time()
    # With re-ranking on, fuse a wider candidate pool, then let the cross-encoder pick top_k.
    candidates = max(cfg.RERANK_CANDIDATES, req.top_k) if cfg.RERANK_ENABLED else req.top_k

    vector_store = PineconeVectorStore(
        embedding=embeddings,
        index_name=PINECONE_INDEX_NAME,
        namespace=req.namespace
    )

    # With LOCALIZE off the search is exactly what it always was (no filter is even passed). The same holds for a
    # namespace outside the taxonomy (coding): its chunks have no labels, so any filter would hide all of them.
    localize = cfg.LOCALIZE != "off" and req.namespace in LOCALIZED_NAMESPACES
    categories = req.categories if localize else None
    bm25_data = await load_bm25(req.namespace)
    chunks = search(vector_store, bm25_data, req, candidates, categories, localize)

    # A wrong frame must cost a wider search, not an empty answer. Widen one step at a time, each step once:
    # level 1 = the parents' family (skipped if the request has none), level 2 = the whole domain with no filter.
    fallback_level = 0
    if localize and categories and not chunks:
        steps = []
        if req.wider_categories:
            steps.append((1, req.wider_categories, True))
        steps.append((2, None, False))
        for fallback_level, wider, filtered in steps:
            logger.info("Nothing found yet in %s; widening to level %d", req.namespace, fallback_level)
            chunks = search(vector_store, bm25_data, req, candidates, wider, filtered)
            if chunks:
                break
    if cfg.RERANK_ENABLED:
        chunks = await asyncio.to_thread(rerank, req.query, chunks, req.top_k)
    else:
        chunks = chunks[: req.top_k]

    print(chunks)

    return RetrievalResponse(
        results=chunks,
        namespace= req.namespace,
        query_time_ms=round((time.time()-start)*1000,2),
        fallback_used=fallback_level > 0,
        fallback_level=fallback_level
    )

