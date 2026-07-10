from typing import TypedDict, Annotated, Literal
from langgraph.graph.message import add_messages

class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    domain: Literal["hr", "legal", "engineering", "coding", "support"] |None
    retrieved_context: list[dict]
    tool_calls_remaining: int
    final_answer: dict| None
    requires_human_reviews: bool

    