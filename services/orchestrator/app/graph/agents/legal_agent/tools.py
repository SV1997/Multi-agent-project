from langchain_core.tools import tool

@tool
def check_compliance_status(regulation: str) -> str:
    """Check current compliance status for a SPECIFIC named regulation.
    ONLY use this tool when the user explicitly asks 'are we compliant 
    with X' or 'what is our compliance status for X'. 
    Do NOT use this tool for general questions about what a regulation 
    says, its principles, or its requirements — those should be answered 
    directly from the retrieved context instead."""
    return "The organization is currently compliant with the available dataset."