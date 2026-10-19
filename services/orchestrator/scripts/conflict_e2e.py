"""Feature 2 (live): ingest two conflicting policy documents, ask, expect both values + review flag.

Needs ingestion and orchestrator running with their secrets. Configure via env:
  INGEST_URL, ORCH_URL, INTERNAL_SHARED_SECRET, EMPLOYEE_EMAIL, and two reachable markdown files
  CONFLICT_DOC_A / CONFLICT_DOC_B whose content says 12 vs 15 annual leave days.
Run:  python scripts/conflict_e2e.py
"""
import os
import sys

import httpx

INGEST_URL = os.getenv("INGEST_URL", "http://localhost:8002/api/v1/ingest")
ORCH_URL = os.getenv("ORCH_URL", "http://localhost:8003/api/v1/query")
HEADERS = {"x-internal-secret": os.getenv("INTERNAL_SHARED_SECRET", "")}
QUESTION = "How many annual leave days does the company policy give?"


def main() -> int:
    docs = [os.environ["CONFLICT_DOC_A"], os.environ["CONFLICT_DOC_B"]]
    with httpx.Client(timeout=120, headers=HEADERS) as c:
        c.post(INGEST_URL, json={"namespace": "hr", "source": [{"path": p, "type": "markdown"} for p in docs]}).raise_for_status()
        r = c.post(ORCH_URL, json={"query": QUESTION, "allowed_namespace": ["hr"], "employee_email": os.environ["EMPLOYEE_EMAIL"]})
        r.raise_for_status()
    body = r.json()
    answer = body.get("answer", "")
    checks = {
        "mentions 12": "12" in answer,
        "mentions 15": "15" in answer,
        "requires_human_review": body.get("requires_human_review") is True,
        "conflict_detected": body.get("conflict_detected") is True,
    }
    print(answer)
    for name, ok in checks.items():
        print(("PASS" if ok else "FAIL"), name)
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
