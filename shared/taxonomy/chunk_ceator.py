import os
from collections import defaultdict
from dotenv import load_dotenv
from pinecone import Pinecone

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
    

def main():
    pc = Pinecone(api_key=os.environ["PINECONE_API_KEY"])
    index = pc.Index(os.environ["PINECONE_INDEX_NAME"])
    with open("taxonomy_inventory.md", "w", encoding="utf-8") as out:
        for ns in NAMESPACES:
            docs = defaultdict(lambda: {"chunks": 0, "first": "", "source": ""})
            for chunk_id, meta in all_chunks(index, ns):
                doc_id = meta.get("source") or "no source stored"
                d = docs[doc_id]
                d["chunks"] += 1
                d["source"] = meta.get("source", "")
                if not d["first"]:
                    d["first"] = " ".join(str(meta.get("text", "")).split())[:200]
            out.write(f"\n## {ns}  ({len(docs)} documents)\n")
            for doc_id, d in sorted(docs.items()):                      
                out.write(f"- {doc_id} | {d['chunks']} chunks | {d['source']}\n    {d['first']}\n")
            print(ns, len(docs), "documents")


if __name__ == "__main__":
    main()