from dotenv import load_dotenv
import os

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
INTERNAL_SHARED_SECRET = os.getenv("INTERNAL_SHARED_SECRET")
RETRIVAL_SERVICE_URL=os.getenv("RETRIVAL_SERVICE_URL", "http://localhost:8001")
CHECKPOINTER_DB_URL=os.getenv("CHECKPOINTER_DB_URL")

CHECKPOINTER_DB_URL = os.environ["CHECKPOINTER_DB_URL"]