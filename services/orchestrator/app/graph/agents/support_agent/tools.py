from langchain_core.tools import tool
from ....core.config import DATABASE_URL
from datetime import datetime
import asyncpg
import uuid

async def get_connection():
    return await asyncpg.connect(DATABASE_URL)

# def check_system_compliance():
#     """
#     Check whether the support function's current ticket-handling process
#     (e.g. data handling in tickets, escalation policy, SLA adherence) is
#     compliant with internal support policy.

#     ONLY use this tool when the user explicitly asks whether support
#     operations ARE currently compliant (e.g. "is the support process
#     compliant with policy?", "are we meeting our SLA compliance
#     requirements?").

#     Do NOT use this tool for general questions about what a support
#     policy, SLA, or escalation process says or requires — those should
#     be answered directly from the retrieved context instead.
#     """

#     return "Your system is compliant with dept policy"
@tool(parse_docstring=True)
async def create_ticket(email: str, purpose: str) -> str:
    """Create a new support ticket for the requesting employee.

    This performs a real action, so use it ONLY when the user explicitly
    asks to create, open, raise, or file a support ticket AND has
    confirmed the purpose in a message that follows your summary.

    Args:
        email: The requesting user's email, recorded as who raised the ticket.
        purpose: A short description of the issue the ticket is for.

    Returns:
        A confirmation with the new ticket ID, or an error message.
    """
    ticket_id = "TKT-" + str(uuid.uuid4())
    conn = await get_connection()
    try:
        await conn.execute(
            'INSERT INTO "TICKETS" (ticket_id, employee_email, pourpose) VALUES ($1,$2,$3)',
            ticket_id, email, purpose,
        )
    except asyncpg.exceptions.ForeignKeyViolationError:
        return f"ERROR: no user found with email {email!r}, so the ticket was NOT created."
    finally:
        await conn.close()

    return f"Ticket {ticket_id} has been created."

TICKET_STATUS= { "pending",
 "resolved",
 "rejected",
 "escalated"}

async def change_ticket_status(ticket_id: str, status: str) -> str:
    """Set the status of an existing support ticket.

    Not exposed to any agent: it has no role check, so it must not be
    reachable by employees who could resolve or dismiss their own tickets.

    Args:
        ticket_id: The ticket's ID, exactly as stored.
        status: The new status: pending, resolved, rejected, or escalated.

    Returns:
        A confirmation with the new status, or an error message.
    """
    if status not in TICKET_STATUS:
        return f"ERROR: status must be one of {sorted(TICKET_STATUS)}, got {status!r}."
    conn = await get_connection()
    try:
        result = await conn.execute(
            'UPDATE "TICKETS" SET status=$1 WHERE ticket_id=$2', status, ticket_id
        )
    finally:
        await conn.close()
    if result == "UPDATE 0":
        return f"ERROR: no ticket found with id {ticket_id!r}."
    return f"Ticket {ticket_id} status changed to {status}."

@tool(parse_docstring=True)
async def escalate_ticket(
    ticket_Id: str,
    email: str,
    reason: str,
)-> str:
    """
    Escalate a support ticket to the next tier of support.

    This performs a real action, so use it ONLY when the user explicitly
    asks to escalate their ticket, raise it to a higher level, or get it
    handled by someone else (e.g. "escalate my ticket", "can you raise
    this to a supervisor", "this hasn't been resolved, escalate it").

    Do NOT use this tool for:
    - Questions about what the escalation process or policy is (answer
      those from the retrieved context instead).
    - Checking a ticket's status (use get_ticket_status for that).
    - A general complaint with no explicit request to escalate.

    Args:
        ticket_Id: The ticket's ID (for example "TKT-1001"), exactly as the user stated it.
        email: The requesting user's email, recorded as who escalated the ticket.
        reason: A short explanation of why the ticket needs escalation.

    Returns:
        A confirmation once the ticket is escalated, or an error message.
    """
    conn = await get_connection()
    try:
        ticket = await conn.fetchrow('SELECT status FROM "TICKETS" WHERE ticket_id=$1', ticket_Id)
        if ticket is None:
            return f"ERROR: no ticket found with id {ticket_Id!r}."
        if ticket["status"] == "escalated":
            return f"Ticket {ticket_Id} is already escalated."

        try:
            async with conn.transaction():
                await conn.execute(
                    'UPDATE "TICKETS" SET status=$1 WHERE ticket_id=$2',
                    "escalated", ticket_Id,
                )
                await conn.execute(
                    'INSERT INTO "TicketReview" ("reviewedByUser", reason, "ticketId") VALUES ($1, $2, $3)',
                    email, reason, ticket_Id
                )
        except asyncpg.exceptions.ForeignKeyViolationError:
            return f"ERROR: no user found with email {email!r}, so the ticket was NOT escalated."

    finally:
        await conn.close()

    return f"Ticket {ticket_Id} has been escalated to the next tier of support."
