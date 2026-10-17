import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), "../../../.."))
import time
from langchain_pinecone import PineconeVectorStore
from shared.embeddings.embeddings import embeddings
from shared.contracts.schema import RetrievalQuery, RetrievalResponse, RetrievedChunk
from ..core.config import PINECONE_INDEX_NAME
from ..storage.bm25score import load_bm25

async def query_namespace(req: RetrievalQuery) -> RetrievalResponse:
    start = time.time()

    vector_store = PineconeVectorStore(
        embedding=embeddings,
        index_name=PINECONE_INDEX_NAME,
        namespace=req.namespace
    )

    results = vector_store.similarity_search_with_score(
        query= req.query,
        k=req.top_k
    )

    bm25_data = await load_bm25(req.namespace)

    rrf_score ={} # Reciprocal Rank Fusion

    meta_lookup = {}

    k=60 # a constant

    for rank,(doc,score) in enumerate(results, start=1):
        rrf_score[doc.page_content] = rrf_score.get(doc.page_content,0)+(1/(k+rank))
        meta_lookup[doc.page_content] = doc.metadata

    if bm25_data is not None:
        bm25_scores = bm25_data["Bm25"].get_scores(req.query.lower().split())
        bm25_chunks = bm25_data["chunks"]

        bm25_ranked = sorted(
            zip(bm25_chunks, bm25_scores), key=lambda x: x[1], reverse=True
        )
        for rank, (chunk, _) in enumerate(bm25_ranked, start=1):
            text = chunk["text"]
            rrf_score[text] = rrf_score.get(text, 0) + 1 / (k + rank)
            if text not in meta_lookup:
                meta_lookup[text] = {"source": chunk["source"]}

    chunks = [
        RetrievedChunk(
            content = text,
            score= float(score),
            source = meta_lookup.get(text, {}).get("source", "unknown"),
            metadata = meta_lookup.get(text, {})
        ) for text, score in rrf_score.items()
    ]
    chunks.sort(key=lambda c: c.score, reverse=True)
    chunks = chunks[: req.top_k]

    print(chunks)

    return RetrievalResponse(
        results=chunks,
        namespace= req.namespace,
        query_time_ms=round((time.time()-start)*1000,2)
    )

