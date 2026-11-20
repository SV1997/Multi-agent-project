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
    # Agent -> supervisor handover. needs_handover: the agent gave up. handed_over: this turn already used its one handover.
    # Both are reset by classify_domain at the start of every turn (the checkpointer keeps state across turns).
    needs_handover: bool
    handed_over: bool
    # Adaptive-retrieval state. These fields make the agent's retrieval
    # decisions inspectable in LangGraph checkpoints and traces.
    original_query: str | None
    search_query: str | None
    retrieval_attempts: int
    max_retrieval_attempts: int
    retrieval_quality: str | None
    retrieval_assessment: str | None
    retrieval_missing: str | None       # what the grader says the passages lack; given to the query rewriter
    tried_queries: list[str]            # every search query used this turn, so a rewrite does not repeat one
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
    # categories the search is narrowed to (set by frame_query_node); None = search the whole domain
    localize_categories: list[str] | None
    # set by frame_query_node: the frames chosen (one, or a few when the question straddles topics), and the sentence
    # added to the answering prompt. The model picks up to 2 frames; their categories are unioned, so a wrong single
    # choice is less likely to hide the right chunks.
    localize_frame_ids: list[str] | None
    localize_wider_categories: list[str] | None     # level 1: the parents' whole family, tried if the first search finds nothing
    localize_scope: str | None                      # the sentence for level 0 (the frame's own categories)
    localize_scope_wider: str | None                # the sentence for level 1 (the parents' family)
    localize_scope_domain: str | None               # the sentence for level 2 (the whole domain)
    # True when the filtered search found nothing and the retrieval service searched the whole domain instead
    localize_fallback_used: bool | None
    localize_fallback_level: int | None             # 0 = the frame's own categories, 1 = the parents' family, 2 = the whole domain
