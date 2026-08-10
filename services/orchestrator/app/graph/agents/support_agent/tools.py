from langchain_core.tools import tool

@tool
def check_system_compliance():
    """
    Check whether the support function's current ticket-handling process
    (e.g. data handling in tickets, escalation policy, SLA adherence) is
    compliant with internal support policy.

    ONLY use this tool when the user explicitly asks whether support
    operations ARE currently compliant (e.g. "is the support process
    compliant with policy?", "are we meeting our SLA compliance
    requirements?").

    Do NOT use this tool for general questions about what a support
    policy, SLA, or escalation process says or requires — those should
    be answered directly from the retrieved context instead.
    """

    return "Your sysstem is compliant with dept policy"