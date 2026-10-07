from rank_bm25 import BM25Okapi
import pickle
import asyncpg
from ..core.config import DATABASE_URL
async def get_connection():
    return await asyncpg.connect(DATABASE_URL)

async def load_bm25(namespace:str):
    conn = await get_connection()

    try:
        row = await conn.fetchrow('SELECT "indexData" FROM bm25_indexes WHERE namespace=$1',
                                  namespace)
        if row is None:
            return None
        return pickle.loads(row["indexData"])
    finally:
        await conn.close()

