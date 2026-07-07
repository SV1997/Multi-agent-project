import os
from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings

load_dotenv()

embeddings = OpenAIEmbeddings(
    model="text-embedding-3-small",
    api_key=os.environ["OPENAI_API_KEY"]
)

def embed_text(text: str) -> list[float]:
    """
    Single string → 1536-dim vector.
    Used by: retrieval-service (one query per user request)
    """
    return embeddings.embed_query(text)

def embed_batch(texts: list[str]) -> list[list[float]]:
    """
    List of strings → list of 1536-dim vectors.
    Used by: ingestion-service (many chunks at once)
    """
    return embeddings.embed_documents(texts)

def get_embedding_dimension() -> int:
    """
    text-embedding-3-small output dimension.
    Used when creating Pinecone index.
    """
    return 1536