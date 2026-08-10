from fastapi import FastAPI
from .api.route import router

app =FastAPI(
    description="Document ingestion pipeline for enterprise RAG platorm",
    version="0.1.0",
    title="ingestion-service"
)

app.include_router(router, prefix="/api/v1")

@app.get("/health")
def health():
    return {"status":"ok", "service":"ingestion-service"}
