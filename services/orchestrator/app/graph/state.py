from typing import TypedDict, Annotated, Literal
from langgraph.graph.message import add_messages

class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    domain: Literal["hr", "legal", "engineering", "coding", "support"] |None
    retrieved_context: list[dict]
    tool_calls_remaining: int
    final_answer: dict| None
    requires_human_review: bool
    allowed_namespace: list[str]
    authorization_denied: bool
    denied_domain: list[str]
    classification_failed: bool
    # Adaptive-retrieval state. These fields make the agent's retrieval
    # decisions inspectable in LangGraph checkpoints and traces.
    original_query: str | None
    search_query: str | None
    retrieval_attempts: int
    max_retrieval_attempts: int
    retrieval_quality: str | None
    retrieval_assessment: str | None
    retrieval_can_use_tool: bool
    retrieval_source: str| None
    retrieval_plan_reason: str | None
    fallback_used: bool | None
    employee_email:str
    long_term_memory: str | None
