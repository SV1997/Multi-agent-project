from rank_bm25 import BM25Okapi

# corpus = [
#     "Employee ID E10001 Name Priya Sharma Floor 4 Tickets Resolved 12",
#     "Employee ID E10032 Name Pallavi Kapoor Floor 7 Tickets Resolved 23",
#     "Employee ID E10033 Name Meera Reddy Floor 9 Tickets Resolved 31",
# ]

# tokenized_corpus = [doc.lower().split() for doc in corpus]
# bm25 = BM25Okapi(tokenized_corpus)

# if __name__== "__main__":
#     query = "How many tickets has E10023 resolved?".lower().split()
#     scores = bm25.get_scores(query)
#     print(scores)

from pinecone import Pinecone
from app.core.config import PINECONE_API_KEY, PINECONE_INDEX_NAME
pc = Pinecone(api_key=PINECONE_API_KEY)
index = pc.Index(PINECONE_INDEX_NAME)
def get_all_chunks_for_namespace(index, namespace: str) -> list[dict]:
    all_chunks = []
    for id_batch in index.list(namespace=namespace):
        fetch_result = index.fetch(ids=id_batch, namespace=namespace)
        for vector_id, vector_data in fetch_result.vectors.items():
            text = vector_data.metadata.get("text", "")
            all_chunks.append({"id": vector_id, "text": text})
    return all_chunks
if __name__=="__main__":
    # index.delete(delete_all=True, namespace="hr")
    # res=get_all_chunks_for_namespace(index,"hr")
    print(index.describe_index_stats())
    # print(res)