from dotenv import load_dotenv
import logging
import os

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
INTERNAL_SHARED_SECRET = os.getenv("INTERNAL_SHARED_SECRET")
RETRIVAL_SERVICE_URL=os.getenv("RETRIVAL_SERVICE_URL", "http://localhost:8001")
CONTEXT_REORDER = os.getenv("CONTEXT_REORDER", "true").lower() == "true"
CHECKPOINTER_DB_URL=os.getenv("CHECKPOINTER_DB_URL")
DATABASE_URL = os.getenv("DATABASE_URL")
SERVICE_HEALTH_URLS = {
    "retrieval-service": os.getenv("RETRIVAL_SERVICE_URL", "http://retrieval-service:8001"),
    "ingestion-service": os.getenv("INGESTION_SERVICE_URL", "http://ingestion-service:8002"),
    "evaluation-service": os.getenv("EVALUATION_SERVICE_URL", "http://evaluation-service:8004"),
    "api-gateway": os.getenv("API_GATEWAY_URL", "http://api-gateway:3000"),
}

# Localized search. "on" = each question is sorted into a frame before the search, the search is narrowed to the
# frame's categories and the answering prompt says what the question is about. "off" = nothing changes.
# Anything else is off. The retrieval service reads its own LOCALIZE setting.
LOCALIZE = os.getenv("LOCALIZE", "off").strip().lower()
if LOCALIZE not in ("on", "off"):
    logging.getLogger(__name__).warning("LOCALIZE=%r is not 'on' or 'off'; using 'off'", LOCALIZE)
    LOCALIZE = "off"
