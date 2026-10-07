from langchain_core.tools import tool
from ....core.config import DATABASE_URL
import asyncpg
import uuid
from decimal import Decimal
async def get_connection():
    return await asyncpg.connect(DATABASE_URL)
# @tool
# def check_expense_for_discrepancy(expense: str) -> str:
#     """
#     Analyze a specific, given expense or invoice entry for discrepancies.

#     ONLY use this tool when the user provides or clearly references a
#     concrete expense/invoice entry and asks you to check it for errors
#     or discrepancies.

#     Do NOT use this tool for general questions about expense policy,
#     reimbursement rules, or budgeting practices — answer those directly
#     from the retrieved context instead.
#     """

#     print(f"[check_expense_for_discrepancy] called with expense:\n{expense}")
#     return "no discrepancy found, expense entry looks consistent"
@tool(parse_docstring=True)
async def create_claim(amount: float, employee_email: str) -> str:
    """Create a new pending expense claim for the requesting employee.

    This performs a real action, so use it ONLY when the user explicitly
    asks to create, submit, or file an expense claim AND has confirmed the
    amount in a message that follows your summary.

    Args:
        amount: The claim amount.
        employee_email: The requesting user's email, recorded as the claim owner.

    Returns:
        A confirmation with the new claim ID, or an error message.
    """
    claim_id = str(uuid.uuid4())
    conn = await get_connection()
    try:
        await conn.execute(
            'INSERT INTO "ExpenseClaim" (claim_id, employee_email, amount, status) VALUES ($1,$2,$3,$4)',
            claim_id, employee_email, Decimal(str(amount)), "pending",
        )
    except asyncpg.exceptions.ForeignKeyViolationError:
        return f"ERROR: no user found with email {employee_email!r}, so the claim was NOT created."
    finally:
        await conn.close()

    return f"Claim {claim_id} has been created with status pending."

CLAIM_STATUSES = {"pending", "approved", "rejected", "flagged"}
@tool(parse_docstring=True)
async def change_claim_status(claim_id: str, status: str) -> str:
    """Set the status of an existing expense claim.

    Not exposed to any agent: it has no role check, so it must not be
    reachable by employees who could approve their own claims.

    Args:
        claim_id: The claim's ID, exactly as stored.
        status: The new status: pending, approved, rejected, or flagged.

    Returns:
        A confirmation with the new status, or an error message.
    """
    if status not in CLAIM_STATUSES:
        return f"ERROR: status must be one of {sorted(CLAIM_STATUSES)}, got {status!r}."
    conn = await get_connection()
    try:
        result = await conn.execute(
            'UPDATE "ExpenseClaim" SET status = $1 WHERE claim_id = $2', status, claim_id
        )
    finally:
        await conn.close()
    if result == "UPDATE 0":
        return f"ERROR: no claim found with id {claim_id!r}."
    return f"Claim {claim_id} status changed to {status}."

@tool(parse_docstring=True)
async def flag_invoice_discrepancy(claim_id: str, reason: str, employee_email: str) -> str:
    """Flag a specific expense claim for human finance review.

    This performs a real action, so use it ONLY when the user explicitly
    asks to flag, escalate, or send a specific expense claim for review
    (e.g. "flag claim CLM-2024-118 for review", "this expense needs a
    second look"). Do not use it for general questions about a claim's
    status or amount - use check_expense_for_discrepancy or the
    retrieved context for those.

    Args:
        claim_id: The claim's ID (for example "CLM-2024-118"), exactly as the user stated it.
        reason: A short explanation of why the claim needs review.
        employee_email: The requesting user's email, recorded as who flagged the claim.

    Returns:
        A confirmation once the claim is flagged, or an error message.
    """
    conn = await get_connection()
    try:
        row = await conn.fetchrow('SELECT status FROM "ExpenseClaim" WHERE claim_id=$1', claim_id)
        if row is None:
            return f"ERROR: no claim found with id {claim_id!r}."
        if row["status"] == "flagged":
            return f"Claim {claim_id} is already flagged for review."

        async with conn.transaction():
            await conn.execute(
                'UPDATE "ExpenseClaim" SET status=$1 WHERE claim_id=$2', "flagged", claim_id
            )
            await conn.execute(
                'INSERT INTO "ExpenseReview" (claim, reason, "reviewedByUser") VALUES ($1,$2,$3)',
                claim_id, reason, employee_email
            )
    finally:
        await conn.close()

    return f"Claim {claim_id} has been flagged for review (status set to flagged)."

