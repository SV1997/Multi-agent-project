FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY services/ingestion_service services/ingestion_service

RUN pip install uv && uv sync --frozen --package ingestion-service

WORKDIR /app/services/ingestion_service

EXPOSE 8002

CMD ["uv","run","--project","/app","uvicorn","app.main:app","--host", "0.0.0.0","--port", "8002"]