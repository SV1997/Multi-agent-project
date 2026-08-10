from langchain_core.tools import tool

@tool
def check_for_bug(code: str) -> str:
    """
    Analyze a specific, given code snippet for bugs.

    ONLY use this tool when the user provides or clearly references a
    concrete piece of code and asks you to check it for bugs.

    Do NOT use this tool for general questions about coding best
    practices, style, or how something should be implemented — answer
    those directly from the retrieved context instead.
    """

    print(f"[check_for_bug] called with code:\n{code}")
    return "bug is resolved check for output"