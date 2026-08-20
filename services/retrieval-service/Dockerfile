FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY shared ./shared
COPY services/retrieval-service ./services/retrieval-service

RUN pip install uv && uv sync --frozen --package retriever-service

WORKDIR /app/services/retrieval-service

ENV PYTHONPATH=/app

EXPOSE 8001

CMD ["uv","run","--project","/app","uvicorn","app.main:app","--host", "0.0.0.0","--port", "8001"]