from dotenv import load_dotenv
import os

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
INTERNAL_SHARED_SECRET = os.getenv("INTERNAL_SHARED_SECRET")