"""contracts_expiring_by_year: manager-only, parameterised, count + value per currency + quotes.
Run from services/retrieval-service: python -m pytest tests/test_contracts_expiring.py   (fake DB)"""
import asyncio
import json
import os
import sys
from contextlib import asynccontextmanager
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))
from app.sql import aggregate_queries as aq  # noqa: E402
from shared.contracts.schema import SQLRetrievalRequest  # noqa: E402


class FakeConn:
    def __init__(self, role, rows):
        self.role, self.rows, self.queries = role, rows, []

    async def fetchval(self, sql, *args):
        return self.role

    async def fetch(self, sql, *args):
        self.queries.append((sql, args))
        return self.rows

    @asynccontextmanager
    async def transaction(self, readonly=False):
        assert readonly is True
        yield

    async def close(self):
        pass


def details(quote):
    return json.dumps({"expiry_date": {"source_quote": quote, "confidence": 0.9}})


ROWS = [
    {"counterparty": "Acme", "expiry_date": date(2027, 3, 31), "value": 120000.0, "currency": "USD", "needs_review": False, "details": details("expires on 31 March 2027")},
    {"counterparty": "Globex", "expiry_date": date(2027, 9, 1), "value": 30000.5, "currency": "USD", "needs_review": True, "details": details("ends 1 Sep 2027")},
    {"counterparty": "Initech", "expiry_date": date(2027, 11, 5), "value": 5000.0, "currency": "EUR", "needs_review": False, "details": details("until 5 November 2027")},
    {"counterparty": "Umbrella", "expiry_date": date(2027, 12, 1), "value": None, "currency": None, "needs_review": True, "details": details("through 1 Dec 2027")},
]


def run(role, rows, data=None, email="m@x.com"):
    conn = FakeConn(role, rows)

    async def fake_conn():
        return conn

    aq.get_connection = fake_conn
    req = SQLRetrievalRequest(employee_email=email, data=data or {}, query="q", namespace="legal", function="contracts_expiring_by_year")
    return asyncio.run(aq.contracts_expiring_by_year(req)), conn


def test_manager_gets_count_totals_and_quotes():
    out, conn = run("admin", ROWS, {"year": "2027"})
    content = out[0]["content"]
    assert content.startswith("4 contract(s) expire in 2027. Total value: EUR 5,000.00; USD 150,000.50 (1 without a value).")
    assert 'Acme - expires 2027-03-31 - USD 120,000.00 - quote: "expires on 31 March 2027"' in content
    assert "Globex" in content and "[needs review]" in content
    assert conn.queries[0][1] == ("legal", 2027)  # parameterised


def test_non_manager_denied_without_querying():
    for role in ("legal_team", "guest", None):
        out, conn = run(role, ROWS)
        assert "Access denied" in out[0]["content"] and conn.queries == []


def test_empty_and_bad_year():
    assert "No contracts" in run("superadmin", [], {"year": "2030"})[0][0]["content"]
    out, conn = run("admin", ROWS, {"year": "next"})
    assert "Invalid year" in out[0]["content"] and conn.queries == []


def test_query_only_counts_documents_typed_as_contract():
    _, conn = run("admin", ROWS, {"year": "2027"})
    assert "document_type = 'contract'" in conn.queries[0][0]
