from fastapi import FastAPI
from contextlib import asynccontextmanager
from psycopg_pool import AsyncConnectionPool
# On Windows, run locally via `python run_dev.py` (not the uvicorn CLI):
# psycopg's async pool can't run on the default ProactorEventLoop, and the
# event loop policy must be switched before uvicorn creates its loop.
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from .core.config import CHECKPOINTER_DB_URL
from .graph.supervisor import set_supervisor_agent

import asyncio

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
        app_state["supervisor"] = set_supervisor_agent(checkpointer)
        yield

app=FastAPI(lifespan=lifespan)
app.include_router(router,prefix="/api/v1")
@app.get("/health")
def health():
    return {"status":"ok", "service":"orchastrator-service"}



def loop_factory(use_subprocess: bool = False) -> asyncio.AbstractEventLoop:
    # psycopg's async pool can't run on Windows' default ProactorEventLoop.
    # uvicorn's built-in "asyncio" loop setup forces ProactorEventLoop on
    # win32 regardless of the process-wide event loop policy, so a custom
    # loop factory must be passed in directly (only possible through the
    # Python API - uvicorn's CLI --loop flag doesn't accept one).
    return asyncio.SelectorEventLoop()


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8003, loop=loop_factory)