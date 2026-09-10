from fastapi import FastAPI
from contextlib import asynccontextmanager
from psycopg_pool import AsyncConnectionPool
# On Windows, run `python -m app.main` from services/orchestrator, or pass
# `--loop app.main:loop_factory` to uvicorn for psycopg compatibility.
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from .core.config import CHECKPOINTER_DB_URL
from .graph.supervisor import set_supervisor_agent
from langgraph.store.postgres import AsyncPostgresStore
import asyncio
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), "../../../../../.."))
from shared.embeddings import embeddings

import uvicorn
app_state = {}

from .api.routes import router

@asynccontextmanager
async def lifespan(asp: FastAPI):
    async with AsyncConnectionPool(
        conninfo=CHECKPOINTER_DB_URL,
        min_size=1,
        max_size=10,
        max_idle=60,
        kwargs={
            "autocommit": True,
            "prepare_threshold": 0,
            "keepalives": 1,
            "keepalives_idle": 30,
            "keepalives_interval": 10,
            "keepalives_count": 3,
        },
        # Neon's pooler silently drops idle backend connections; re-verify
        # each connection before handing it out instead of trusting a
        # possibly-dead socket.
        check=AsyncConnectionPool.check_connection,
        open=False,
    ) as pool:
        await pool.open(wait=True)
        checkpointer = AsyncPostgresSaver(pool)
        async with AsyncPostgresStore.from_conn_string(
            CHECKPOINTER_DB_URL,
            index={"embed":embeddings,"dims":1536}
        ) as store:
            await store.setup()
            app_state["supervisor"] = set_supervisor_agent(checkpointer, store)
            app_state["memory_store"] = store
            yield

app=FastAPI(lifespan=lifespan)
app.include_router(router,prefix="/api/v1")
@app.get("/health")
def health():
    return {"status":"ok", "service":"orchastrator-service"}



def loop_factory(use_subprocess: bool = False) -> asyncio.AbstractEventLoop:
    # psycopg's async pool can't run on Windows' default ProactorEventLoop.
    # Pass this factory by import string so uvicorn selects it before startup.
    return asyncio.SelectorEventLoop()


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8003, loop="app.main:loop_factory")
