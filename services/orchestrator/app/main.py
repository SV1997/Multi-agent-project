from fastapi import FastAPI
from contextlib import asynccontextmanager
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from .core.config import CHECKPOINTER_DB_URL
from .graph.supervisor import set_supervisor_agent

app_state = {}

from .api.routes import router

@asynccontextmanager
async def lifespan(asp: FastAPI):
    async with AsyncPostgresSaver.from_conn_string(CHECKPOINTER_DB_URL) as checkpointer:
        app_state["supervisor"]= set_supervisor_agent(checkpointer)
        yield

app=FastAPI(lifespan=lifespan)
app.include_router(router,prefix="/api/v1")
@app.get("/health")
def health():
    return {"status":"ok", "service":"orchastrator-service"}
