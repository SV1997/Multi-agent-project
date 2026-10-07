from dotenv import load_dotenv
import os

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
INTERNAL_SHARED_SECRET = os.getenv("INTERNAL_SHARED_SECRET")
RETRIVAL_SERVICE_URL=os.getenv("RETRIVAL_SERVICE_URL", "http://localhost:8001")
CHECKPOINTER_DB_URL=os.getenv("CHECKPOINTER_DB_URL")
DATABASE_URL = os.getenv("DATABASE_URL")
SERVICE_HEALTH_URLS = {
    "retrieval-service": os.getenv("RETRIVAL_SERVICE_URL", "http://retrieval-service:8001"),
    "ingestion-service": os.getenv("INGESTION_SERVICE_URL", "http://ingestion-service:8002"),
    "evaluation-service": os.getenv("EVALUATION_SERVICE_URL", "http://evaluation-service:8004"),
    "api-gateway": os.getenv("API_GATEWAY_URL", "http://api-gateway:3000"),
}
