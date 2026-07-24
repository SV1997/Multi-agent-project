import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from langgraph.checkpoint.postgres import PostgresSaver
from app.core.config import CHECKPOINTER_DB_URL

def main():
    with PostgresSaver.from_conn_string(CHECKPOINTER_DB_URL) as checkpointer:
        checkpointer.setup()
        print("Checkpointer tables created successfully.")

if __name__ == "__main__":
    main()