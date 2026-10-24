from langchain_core.tools import tool
import asyncpg
from ....core.config import DATABASE_URL
from datetime import datetime

async def get_connection():
    return await asyncpg.connect(DATABASE_URL)

@tool(parse_docstring=True)
async def submit_leave_request(
    employeeid: str,
    leave_type: str,
    start_date: str,
    end_date: str,
    reason: str = "",
) -> str:
    """Submit a leave request on behalf of an employee.

    This files a real request, so call it only after the user has asked to
    apply for leave AND has explicitly confirmed the details you summarised.
    Do not use it for leave policy questions, balance checks, or approvals.

    Args:
        employeeid: The employee's email, exactly as the user stated it.
        leave_type: The leave category as named in the knowledge base (for example "casual leave").
        start_date: First day of leave in ISO format YYYY-MM-DD.
        end_date: Last day of leave in ISO format YYYY-MM-DD, on or after start_date.
        reason: Optional reason given by the user. Empty string if none was given.

    Returns:
        A confirmation with a request reference on success, or an error message.
    """
    try:
        date1 = datetime.strptime(start_date, "%Y-%m-%d")
        date2 = datetime.strptime(end_date, "%Y-%m-%d")
    except ValueError:
        return f"ERROR: dates must be in YYYY-MM-DD format, got start_date={start_date!r} end_date={end_date!r}."

    if date2 < date1:
        return "ERROR: end_date is before start_date."

    gap = (date2 - date1).days + 1

    conn = await get_connection()
    try:
        async with conn.transaction():
            employee = await conn.fetchrow(
                'SELECT leave_balance FROM "EmployeeData" WHERE employee_email = $1',
                employeeid,
            )
            if employee is None:
                return f"ERROR: no employee record found for {employeeid!r}. Leave request was NOT submitted."
            if employee["leave_balance"] < gap:
                return (
                    f"ERROR: requested {gap} day(s) but {employeeid} only has "
                    f"{employee['leave_balance']} day(s) remaining. Leave request was NOT submitted."
                )

            await conn.execute(
                'UPDATE "EmployeeData" SET leave_balance = leave_balance - $1 WHERE employee_email = $2',
                gap, employeeid,
            )
            record = await conn.fetchrow(
                """
                INSERT INTO "LeaveRecord" (leave_applied_by, start_date, end_date, total_number_of_days, leave_type, reason)
                VALUES ($1, $2, $3, $4, $5,$6)
                RETURNING id
                """,
                employeeid, date1, date2, gap,leave_type, reason
            )
    finally:
        await conn.close()

    return (
        f"Leave request submitted. Reference #{record['id']}: {leave_type} for {employeeid}, "
        f"{start_date} to {end_date} ({gap} day(s)). Reason: {reason or 'not given'}."
    )
