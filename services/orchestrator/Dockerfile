FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY shared ./shared
COPY services/orchestrator ./services/orchestrator

RUN pip install uv && uv sync --frozen --package orchestrator

WORKDIR /app/services/orchestrator

ENV PYTHONPATH=/app

EXPOSE 8003

CMD ["uv","run","--project","/app","uvicorn","app.main:app","--host", "0.0.0.0","--port", "8003"]