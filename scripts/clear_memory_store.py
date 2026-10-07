import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "services", "orchestrator", ".env"))

DATABASE_URL = os.environ["CHECKPOINTER_DB_URL"]
NAMESPACE = "saharsh_vashishtha@gmail_com".replace(".", "_")


async def main():
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        rows = await conn.fetch("SELECT key FROM store WHERE prefix = $1", NAMESPACE)
        print(f"Found {len(rows)} memory entries for namespace '{NAMESPACE}':")
        for r in rows:
            print(" -", r["key"])

        if not rows:
            return

        confirm = input("\nDelete all of these? [y/N] ")
        if confirm.strip().lower() != "y":
            print("Aborted, nothing deleted.")
            return

        deleted = await conn.fetch("DELETE FROM store WHERE prefix = $1 RETURNING key", NAMESPACE)
        print(f"Deleted {len(deleted)} rows (store_vectors rows cascade-deleted automatically).")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
