import os
from dotenv import load_dotenv
from pinecone import Pinecone

load_dotenv()

NAMESPACE = "finance"

pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
index = pc.Index(os.getenv("PINECONE_INDEX_NAME"))

before = index.describe_index_stats()
print("before:", before.namespaces.get(NAMESPACE))

# index.delete(delete_all=True, namespace=NAMESPACE)

# after = index.describe_index_stats()
# print("after:", after.namespaces.get(NAMESPACE))