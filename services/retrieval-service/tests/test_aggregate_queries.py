"""Feature 4: aggregate SQL functions enforce the manager check. Run from services/retrieval-service:
python -m pytest tests/test_aggregate_queries.py   (uses a fake connection; no DB needed)"""
import asyncio
import os
import sys
from contextlib import asynccontextmanager

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


def run(fn, role, rows, data=None, email="m@x.com"):
    conn = FakeConn(role, rows)

    async def fake_conn():
        return conn

    aq.get_connection = fake_conn
    req = SQLRetrievalRequest(employee_email=email, data=data or {}, query="q", namespace="finance", function=fn.__name__)
    return asyncio.run(fn(req)), conn


CLAIMS = [{"status": "pending", "n": 3, "total": 1200.5}, {"status": "approved", "n": 5, "total": 800.0}]
LEAVE = [{"month": 1, "days": 4}, {"month": 3, "days": 7}]


def test_manager_gets_exact_claim_numbers():
    out, _ = run(aq.claims_by_status_for_team, "admin", CLAIMS, {"team": "finance_team"})
    assert out[0]["content"] == (
        "Expense claims for finance_team by status: pending=3 (total 1200.50), approved=5 (total 800.00), "
        "rejected=0 (total 0.00), flagged=0 (total 0.00)")


def test_manager_gets_exact_leave_by_month():
    out, conn = run(aq.leave_taken_by_month, "superadmin", LEAVE, {"year": "2026"})
    assert out[0]["content"] == "Leave days taken in 2026 for all teams by month: Jan=4, Mar=7"
    assert conn.queries[0][1] == (2026, None)  # parameterised, not interpolated


def test_non_manager_denied_without_querying():
    for role in ("hr_team", "finance_team", "guest", None):
        for fn in (aq.claims_by_status_for_team, aq.leave_taken_by_month):
            out, conn = run(fn, role, CLAIMS)
            assert "Access denied" in out[0]["content"] and conn.queries == []


def test_missing_email_denied():
    out, conn = run(aq.claims_by_status_for_team, "admin", CLAIMS, email="")
    assert "Access denied" in out[0]["content"] and conn.queries == []


def test_bad_team_and_year_rejected():
    out, conn = run(aq.claims_by_status_for_team, "admin", CLAIMS, {"team": "x'; DROP TABLE"})
    assert "Unknown team" in out[0]["content"] and conn.queries == []
    out, _ = run(aq.leave_taken_by_month, "admin", LEAVE, {"year": "abc"})
    assert "Invalid year" in out[0]["content"]
