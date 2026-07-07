from fastapi import FastAPI

from .api.routes import router

app = FastAPI(
    title="retrieval-service",
    description="Pinecone namespace query service for enterprise Rag platform",
    version="0.1.0"
)

app.include_router(router, prefix="/api/v1")

@app.get("/health")
async def health():
    return {"status":"ok", "service": "retrieval-service"}