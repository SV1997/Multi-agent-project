import asyncio
from fastapi import FastAPI
from contextlib import asynccontextmanager
from psycopg_pool import AsyncConnectionPool

def loop_factory() -> asyncio.AbstractEventLoop:
    # psycopg's async pool can't run on Windows' default ProactorEventLoop.
    # Irrelevant on Linux (the deployment target) - only needed to run locally
    # on Windows via: uvicorn app.main:app --loop app.main:loop_factory
    return asyncio.SelectorEventLoop()
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from .core.config import CHECKPOINTER_DB_URL
from .graph.supervisor import set_supervisor_agent

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
