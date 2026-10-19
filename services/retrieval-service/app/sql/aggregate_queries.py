import json
import sys
import os
from datetime import datetime, timezone
from decimal import Decimal
sys.path.append(os.path.join(os.path.dirname(__file__), "../../../.."))
from shared.contracts.schema import SQLRetrievalRequest
from .sql_queries import get_connection

# No manager/reporting-line model exists yet, so "manager or above" is the admin roles.
MANAGER_ROLES = frozenset({"admin", "superadmin"})
TEAM_ROLES = frozenset({"legal_team", "hr_team", "support_team", "finance_team", "engineering_team"})
CLAIM_STATUSES = ("pending", "approved", "rejected", "flagged")
MAX_LISTED_CONTRACTS = 20


def _denied(name: str) -> list[dict]:
    return [{"source": f"sql:{name}", "content": "Access denied: team-level aggregates require a manager or higher role."}]


async def _is_manager(conn, email: str | None) -> bool:
    """Role comes from the User table, never from the request. Unknown user or role -> False (fail closed)."""
    if not email:
        return False
    role = await conn.fetchval('SELECT role::text FROM "User" WHERE "Email" = $1', email)
    return role in MANAGER_ROLES


def _team_param(data) -> tuple[str | None, str | None]:
    """Returns (team, error). team=None means all employees."""
    team = (data or {}).get("team")
    if not team:
        return None, None
    if team not in TEAM_ROLES:
        return None, f"Unknown team '{team}'. Valid teams: {', '.join(sorted(TEAM_ROLES))}."
    return team, None


async def claims_by_status_for_team(req: SQLRetrievalRequest) -> list[dict]:
    name = "claims_by_status_for_team"
    conn = await get_connection()
    try:
        if not await _is_manager(conn, req.employee_email):
            return _denied(name)
        team, error = _team_param(req.data)
        if error:
            return [{"source": f"sql:{name}", "content": error}]
        async with conn.transaction(readonly=True):
            rows = await conn.fetch(
                'SELECT c.status::text AS status, COUNT(*)::int AS n, COALESCE(SUM(c.amount), 0)::float AS total '
                'FROM "ExpenseClaim" c JOIN "User" u ON u."Email" = c.employee_email '
                'WHERE ($1::text IS NULL OR u.role::text = $1) GROUP BY c.status',
                team,
            )
        by_status = {r["status"]: r for r in rows}
        parts = [
            f"{s}={by_status[s]['n'] if s in by_status else 0} (total {by_status[s]['total'] if s in by_status else 0:.2f})"
            for s in CLAIM_STATUSES
        ]
        return [{"source": f"sql:{name}", "content": f"Expense claims for {team or 'all teams'} by status: " + ", ".join(parts)}]
    finally:
        await conn.close()


async def leave_taken_by_month(req: SQLRetrievalRequest) -> list[dict]:
    """Leave days per month (by leave start date) for a calendar year; a leave spanning months counts in its start month."""
    name = "leave_taken_by_month"
    conn = await get_connection()
    try:
        if not await _is_manager(conn, req.employee_email):
            return _denied(name)
        team, error = _team_param(req.data)
        if error:
            return [{"source": f"sql:{name}", "content": error}]
        raw_year = (req.data or {}).get("year")
        try:
            year = int(raw_year) if raw_year else datetime.now(timezone.utc).year
        except (TypeError, ValueError):
            return [{"source": f"sql:{name}", "content": f"Invalid year '{raw_year}'."}]
        async with conn.transaction(readonly=True):
            rows = await conn.fetch(
                'SELECT EXTRACT(MONTH FROM l.start_date)::int AS month, SUM(l.total_number_of_days)::int AS days '
                'FROM "LeaveRecord" l JOIN "User" u ON u."Email" = l.leave_applied_by '
                'WHERE EXTRACT(YEAR FROM l.start_date) = $1 AND ($2::text IS NULL OR u.role::text = $2) '
                'GROUP BY 1 ORDER BY 1',
                year, team,
            )
        if not rows:
            return [{"source": f"sql:{name}", "content": f"No leave recorded for {team or 'all teams'} in {year}."}]
        months = ", ".join(f"{datetime(year, r['month'], 1):%b}={r['days']}" for r in rows)
        return [{"source": f"sql:{name}", "content": f"Leave days taken in {year} for {team or 'all teams'} by month: {months}"}]
    finally:
        await conn.close()


def _year_param(data) -> tuple[int, str | None]:
    raw_year = (data or {}).get("year")
    try:
        return (int(raw_year) if raw_year else datetime.now(timezone.utc).year), None
    except (TypeError, ValueError):
        return 0, f"Invalid year '{raw_year}'."


async def contracts_expiring_by_year(req: SQLRetrievalRequest) -> list[dict]:
    """Contracts whose extracted expiry date falls in a year: count, value per currency, and the list with source quotes."""
    name = "contracts_expiring_by_year"
    conn = await get_connection()
    try:
        if not await _is_manager(conn, req.employee_email):
            return _denied(name)
        year, error = _year_param(req.data)
        if error:
            return [{"source": f"sql:{name}", "content": error}]
        async with conn.transaction(readonly=True):
            rows = await conn.fetch(
                'SELECT counterparty, expiry_date, value, currency, needs_review, details FROM doc_extractions '
                'WHERE namespace = $1 AND EXTRACT(YEAR FROM expiry_date) = $2 ORDER BY expiry_date, doc_id',
                "legal", year,
            )
        if not rows:
            return [{"source": f"sql:{name}", "content": f"No contracts with an extracted expiry date in {year}."}]
        totals: dict[str, Decimal] = {}
        no_value = 0
        lines = []
        for i, r in enumerate(rows, 1):
            if r["value"] is None:
                no_value += 1
            else:
                totals[r["currency"] or "unknown currency"] = totals.get(r["currency"] or "unknown currency", Decimal(0)) + Decimal(str(r["value"]))
            details = json.loads(r["details"]) if isinstance(r["details"], str) else (r["details"] or {})
            quote = (details.get("expiry_date") or {}).get("source_quote")
            value = f"{r['currency'] or ''} {Decimal(str(r['value'])):,.2f}".strip() if r["value"] is not None else "value unknown"
            lines.append(
                f"{i}. {r['counterparty'] or 'unknown counterparty'} - expires {r['expiry_date']} - {value} - "
                f"quote: \"{quote}\"" + (" [needs review]" if r["needs_review"] else "")
            )
        total_text = "; ".join(f"{cur} {amt:,.2f}" for cur, amt in sorted(totals.items())) or "none"
        extra = f" ({no_value} without a value)" if no_value else ""
        shown = lines[:MAX_LISTED_CONTRACTS]
        more = [f"...and {len(lines) - MAX_LISTED_CONTRACTS} more"] if len(lines) > MAX_LISTED_CONTRACTS else []
        content = f"{len(rows)} contract(s) expire in {year}. Total value: {total_text}{extra}.\n" + "\n".join(shown + more)
        return [{"source": f"sql:{name}", "content": content}]
    finally:
        await conn.close()
