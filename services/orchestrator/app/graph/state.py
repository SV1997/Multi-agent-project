from typing import TypedDict, Annotated, Literal
from langgraph.graph.message import add_messages

class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    domain: Literal["hr", "legal", "engineering", "finance", "support"] |None
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
    react_trace: list[dict]
    turn: str | None
    thread_facts: str |None
    conversation_memories: list[str] |None
    search_failures: int
    # categories the search is narrowed to (set by the query frame); None = search the whole domain
    localize_categories: list[str] | None
    # the query frame step (app/graph/frames): the chosen frame, the slots the user gave, what is still missing,
    # the question to ask if something is, the question rewritten to stand on its own, and the trace of it all
    frame_id: str | None
    frame_slots: dict | None
    missing_slots: list[str] | None
    clarifying_question: str | None
    rewritten_query: str | None
    query_dag: dict | None
    asked_frame_id: str | None      # the frame that asked a clarifying question; remembered for the next turn only
