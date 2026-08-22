FROM python:3.14-slim

WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY shard ./shared
COPY  services/ingestion_service ./services/ingestion_service

RUN pip install uv && uv sync --frozen --package ingestion-service

WORKDIR /app/services/ingestion_ervice

EXPOSE 8002

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]

