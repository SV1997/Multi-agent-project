# Build context must be the repo root, e.g.:
#   docker build -f services/orchestrator/Dockerfile -t orchestrator .
# (the app reaches into ../../../../shared for shared/contracts/schema.py,
# so the "shared" package needs to sit next to services/ inside the image)

FROM python:3.14-slim

WORKDIR /app

COPY shared/ ./shared/
COPY services/orchestrator/ ./services/orchestrator/

RUN pip install --no-cache-dir \
    ./services/orchestrator \
    fastapi \
    "uvicorn[standard]" \
    python-dotenv

WORKDIR /app/services/orchestrator

EXPOSE 8003

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8003"]
