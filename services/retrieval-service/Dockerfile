FROM python:3.14-slim

WORKDIR /app

RUN pip install uv

# Dependencies first: this layer is rebuilt only when a pyproject.toml or uv.lock changes,
# not on every code edit. All workspace members' manifests are needed to resolve the lock.
COPY pyproject.toml uv.lock ./
COPY services/retrieval-service/pyproject.toml services/retrieval-service/pyproject.toml
COPY services/orchestrator/pyproject.toml services/orchestrator/pyproject.toml
COPY services/ingestion_service/pyproject.toml services/ingestion_service/pyproject.toml
COPY services/evaluation_service/pyproject.toml services/evaluation_service/pyproject.toml
COPY locust-test/pyproject.toml locust-test/pyproject.toml
RUN uv sync --frozen --package retrieval-service --no-install-workspace

COPY shared ./shared
COPY services/retrieval-service ./services/retrieval-service
RUN uv sync --frozen --package retrieval-service

WORKDIR /app/services/retrieval-service

ENV PYTHONPATH=/app

EXPOSE 8001

CMD ["uv","run","--project","/app","uvicorn","app.main:app","--host", "0.0.0.0","--port", "8001"]