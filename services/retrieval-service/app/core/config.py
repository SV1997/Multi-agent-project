import os
from dotenv import load_dotenv
load_dotenv()

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME")
INTERNAL_SHARED_SECRET = os.getenv("INTERNAL_SHARED_SECRET")