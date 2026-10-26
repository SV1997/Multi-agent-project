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

# Localized search. off = exactly today's behaviour. filter / prompt / full = searches only look at chunks that
# are content and (when the request names categories) are in those categories. An unknown value counts as off.
LOCALIZE_LEVELS = ("off", "filter", "prompt", "full")
LOCALIZE = os.getenv("LOCALIZE", "off").strip().lower()
if LOCALIZE not in LOCALIZE_LEVELS:
    logging.getLogger(__name__).warning("LOCALIZE=%r is not one of %s; using 'off'", LOCALIZE, LOCALIZE_LEVELS)
    LOCALIZE = "off"
