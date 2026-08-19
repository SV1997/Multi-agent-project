FROM python:3.14-slim

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY shared ./shared
COPY services/evaluation_service ./services/evaluation_service

RUN pip install uv && uv sync --frozen --package evaluation-service

WORKDIR /app/services/evaluation_service

EXPOSE 8004

CMD ["uv", "run", "--project", "/app", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8004"]