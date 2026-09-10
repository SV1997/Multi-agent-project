from fastapi import FastAPI
from .api.route import router

app =FastAPI(
    description="Ragas-based answer evaluation for enterprise RAG platform",
    version="0.1.0",
    title="evaluation-service"
)

app.include_router(router, prefix="/api/v1")

@app.get("/health")
def health():
    return {"status":"ok", "service":"evaluation-service"}
