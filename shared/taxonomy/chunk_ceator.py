from dotenv import load_dotenv

load_dotenv()                                   
NAMESPACES = ["hr", "legal", "finance", "support", "engineering"]


def all_chunks(index, namespace):
    """Yield (chunk_id, metadata) for every chunk in one namespace."""
    ids = []
    for page in index.list(namespace=namespace):    
        ids.extend(page)
    for start in range(0, len(ids), 100):            
        batch = ids[start:start + 100]
        vectors = index.fetch(ids=batch, namespace=namespace).vectors
        for chunk_id in batch:
            if chunk_id in vectors:
                yield chunk_id, dict(vectors[chunk_id].metadata or {})
