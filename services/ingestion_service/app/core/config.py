import os
from dotenv import load_dotenv
load_dotenv()

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME")
INTERNAL_SHARED_SECRET = os.getenv("INTERNAL_SHARED_SECRET")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", '500'))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP","50"))