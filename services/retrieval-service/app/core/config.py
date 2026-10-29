import logging
import os
from dotenv import load_dotenv
load_dotenv()

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME")
INTERNAL_SHARED_SECRET = os.getenv("INTERNAL_SHARED_SECRET")
DATABASE_URL = os.getenv("DATABASE_URL")
RERANK_ENABLED = os.getenv("RERANK_ENABLED", "false").lower() == "true"
RERANK_MODEL = os.getenv("RERANK_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")
RERANK_CANDIDATES = int(os.getenv("RERANK_CANDIDATES", "20"))

# Localized search. "on" = a request that names categories only searches chunks in those categories (and searches the
# whole domain once if that finds nothing). "off" = every search covers the whole domain. Anything else is off.
LOCALIZE = os.getenv("LOCALIZE", "off").strip().lower()
if LOCALIZE not in ("on", "off"):
    logging.getLogger(__name__).warning("LOCALIZE=%r is not 'on' or 'off'; using 'off'", LOCALIZE)
    LOCALIZE = "off"
