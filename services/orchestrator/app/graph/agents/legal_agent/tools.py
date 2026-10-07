from langchain_core.tools import tool
from ....core.config import DATABASE_URL
import asyncpg
import uuid
from datetime import datetime
async def get_connection():
    return await asyncpg.connect(DATABASE_URL)
# @tool
# def check_compliance_status(regulation: str) -> str:
#     """Check current compliance status for a SPECIFIC named regulation.
#     ONLY use this tool when the user explicitly asks 'are we compliant
#     with X' or 'what is our compliance status for X'.
#     Do NOT use this tool for general questions about what a regulation
#     says, its principles, or its requirements — those should be answered
#     directly from the retrieved context instead."""
#     return "The organization is currently compliant with the available dataset."
@tool(parse_docstring=True)
async def create_contract(counterparty: str, summary: str, managed_by_email: str, expiry_date: str) -> str:
    """Create a new legal contract record.

    This performs a real action, so use it ONLY when the user explicitly
    asks to create, draft, or add a new contract AND has confirmed the
    details in a message that follows your summary.

    Args:
        counterparty: The other party's name on the contract.
        summary: A short description of what the contract covers.
        managed_by_email: The requesting user's email, recorded as who manages the contract.
        expiry_date: The contract's expiry date in ISO format YYYY-MM-DD.

    Returns:
        A confirmation with the new contract number, or an error message.
    """
    try:
        parsed_expiry = datetime.strptime(expiry_date, "%Y-%m-%d")
    except ValueError:
        return f"ERROR: expiry_date must be in YYYY-MM-DD format, got {expiry_date!r}."

    contract_number = "LC-" + str(uuid.uuid4())
    conn = await get_connection()
    try:
        await conn.execute('''INSERT INTO "LegalContract"
        (contract_number, counterparty, managed_by_email, expiry_date, summary, "updatedAt")
        VALUES ($1, $2,$3,$4,$5,$6)
        ''', contract_number, counterparty, managed_by_email, parsed_expiry, summary, datetime.now())

    except asyncpg.exceptions.ForeignKeyViolationError:
        return f"ERROR: no user found with email {managed_by_email!r}, so the contract was NOT created."

    finally:
        await conn.close()

    return f"The contract with contract number {contract_number} has been created."

CONTRACT_STATUSES = {  "active",
  "expiring_soon",
  "expired",
  "under_negotiation",
  "under_review",
  }

@tool(parse_docstring=True)
async def change_contract_status(contract_number: str, status: str) -> str:
    """Set the status of an existing legal contract.

    Not exposed to any agent: it has no role check, so it must not be
    reachable by employees who could approve their own contracts.

    Args:
        contract_number: The contract's number, exactly as stored.
        status: The new status: active, expiring_soon, expired,
            under_negotiation, or under_review.

    Returns:
        A confirmation with the new status, or an error message.
    """
    if status not in CONTRACT_STATUSES:
        return f"ERROR: status must be one of {sorted(CONTRACT_STATUSES)}, got {status!r}."
    conn = await get_connection()
    try:
        result = await conn.execute(
            'UPDATE "LegalContract" SET status = $1 WHERE contract_number=$2', status, contract_number
        )
    finally:
        await conn.close()
    if result == "UPDATE 0":
        return f"ERROR: no contract found with number {contract_number!r}."
    return f"Contract {contract_number} status changed to {status}."

@tool(parse_docstring=True)
async def flag_contract_for_review(contract_number: str, reason: str, email: str) -> str:
    """Flag a specific contract for human legal review.

    This performs a real action, so use it ONLY when the user explicitly
    asks to flag, escalate, or send a specific contract for review (e.g.
    "flag contract C-2024-118 for review", "this contract needs legal to
    look at it again").

    Do NOT use this tool for general questions about a contract's terms,
    status, or expiry — those should be answered from the retrieved
    context or contract_tracking instead. Do not invent a contract
    number that was not explicitly given in the conversation.

    Args:
        contract_number: The contract's number (for example "C-2024-118"), exactly as the user stated it.
        reason: A short explanation of why the contract needs review.
        email: The requesting user's email, recorded as who flagged the contract.

    Returns:
        A confirmation once the contract is flagged, or an error message.
    """
    conn = await get_connection()
    try:
        contract = await conn.fetchrow(
            'SELECT status FROM "LegalContract" WHERE contract_number=$1',
            contract_number,
        )
        if contract is None:
            return f"ERROR: no contract found with number {contract_number!r}."

        existing_review = await conn.fetchrow(
            'SELECT id FROM "ContractReview" WHERE contract=$1 AND "reviewedByUser"=$2',
            contract_number, email,
        )
        if contract["status"] == "under_review" and existing_review is not None:
            return f"You have already flagged contract {contract_number} for review."

        async with conn.transaction():
            await conn.execute(
                'UPDATE "LegalContract" SET status=$1 WHERE contract_number=$2',
                "under_review", contract_number,
            )
            await conn.execute(
                'INSERT INTO "ContractReview" (contract, "reviewedByUser", reason) VALUES ($1, $2, $3)',
                contract_number, email, reason,
            )
    finally:
        await conn.close()
    return f"Contract {contract_number} has been flagged for review (status set to under_review)."
