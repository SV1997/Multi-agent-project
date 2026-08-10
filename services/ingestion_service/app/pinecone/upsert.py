from langchain_pinecone import PineconeVectorStore
import os
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), "../../../.."))
from shared.embeddings.embeddings import embeddings
from langchain_core.documents import Document
from ..core.config import PINECONE_INDEX_NAME

def upsert_document(
        documents: list[Document],
        namespace: str
) -> int:
    PineconeVectorStore.from_documents(
        documents=documents,
        embedding=embeddings,
        index_name= PINECONE_INDEX_NAME,
        namespace=namespace
    )
    return len(documents)