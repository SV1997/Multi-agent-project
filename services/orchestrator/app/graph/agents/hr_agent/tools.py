from langchain_core.tools import tool

@tool
def check_balance_leaves(employeeid:str)->str:
    """
    Look up an employee's current remaining leave balance from the HR
    database, given their employee ID.

    Call this tool whenever the user asks, in any wording, how many
    leave days/leaves they or another employee have left, remaining,
    available, or accrued - e.g. "how many leaves do I have left",
    "what's my leave balance", "check my leaves", "remaining PTO for
    employee E1042", or a follow-up like "and for employee E2001?".
    This includes indirect phrasings, not just exact matches.

    Requires a concrete employee ID. If the user hasn't given one
    (in this message or earlier in the conversation), do NOT call
    this tool with a placeholder or guessed ID - ask the user for
    their employee ID first, then call this tool once you have it.

    Do NOT call this tool for: leave approval requests, leave
    applications, leave encashment, general leave policy questions,
    or questions about types/categories of leave available. Answer
    those from the retrieved knowledge-base context instead - the
    context never contains a specific person's live balance, only
    this tool does.
    """

    # TODO: wire up to the real employee/HR database. Until then, this stub
    # deliberately returns no numeric data so the agent cannot pass off a
    # fabricated leave count as real.
    return "TOOL_NOT_IMPLEMENTED: no leave balance data source is connected yet."