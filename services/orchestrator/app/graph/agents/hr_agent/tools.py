from langchain_core.tools import tool

@tool
def check_balance_leaves(employeeid:str)->str:
    """
    Check for the balance leaves of employee which is fetched from employee id from the database.
    This tool is used only to check the leaves balance. never use it for leave approval or when emplyee apply for leave 
    or leave encashment. 
    Do not use this question for general use like leave policy or checking for type of leaves
    """

    # TODO: wire up to the real employee/HR database. Until then, this stub
    # deliberately returns no numeric data so the agent cannot pass off a
    # fabricated leave count as real.
    return "TOOL_NOT_IMPLEMENTED: no leave balance data source is connected yet."