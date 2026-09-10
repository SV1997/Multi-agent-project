import os
from dotenv import load_dotenv
load_dotenv()


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
INTERNAL_SHARED_SECRET = os.getenv("INTERNAL_SHARED_SECRET")
