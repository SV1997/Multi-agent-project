import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), "../../../.."))
import time
from langchain_pinecone import PineconeVectorStore
from shared.embeddings.embeddings import embeddings
from shared.contracts.schema import RetrievalQuery, RetrievalResponse, RetrievedChunk
from ..core.config import PINECONE_INDEX_NAME

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

    chunks = [
        RetrievedChunk(
            content = doc.page_content,
            score= float(score),
            source = doc.metadata.get("source", ""),
            metadata = doc.metadata
        ) for doc, score in results
    ]

    return RetrievalResponse(
        results=chunks,
        namespace= req.namespace,
        query_time_ms=round((time.time()-start)*1000,2)
    )

