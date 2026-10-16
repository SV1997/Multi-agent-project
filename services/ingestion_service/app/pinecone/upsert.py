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
from ..core.config import PINECONE_INDEX_NAME
import asyncpg

def upsert_document(
        documents: list[Document],
        namespace: str,
        doc_id: Optional[str] = None,
        effective_date: Optional[str] = None,
) -> int:
    PineconeVectorStore.from_documents(
        documents=documents,
        embedding=embeddings,
        index_name= PINECONE_INDEX_NAME,
        namespace=namespace
    )
    return len(documents)
