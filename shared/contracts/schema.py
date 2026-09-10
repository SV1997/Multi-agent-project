# shared/schemas/contracts.py
"""
Shared Pydantic contracts used across all services (orchestrator, retrieval-service,
ingestion-service, tool-service, evaluation-service). Node.js services use the
equivalent Zod schema (shared/schemas/contracts.ts) to keep wire format in sync.
"""

from pydantic import BaseModel, Field
from typing import Any, Literal, Optional
from datetime import datetime


# ---- Retrieval contracts ----

class RetrievalQuery(BaseModel):
    query: str
    namespace: Literal["legal", "hr", "engineering", "coding", "support"]
    top_k: int = 5


class RetrievedChunk(BaseModel):
    content: str
    score: float
    source: str
    metadata: dict = Field(default_factory=dict)


class RetrievalResponse(BaseModel):
    results: list[RetrievedChunk]
    namespace: str
    query_time_ms: float

class SQLRetrievalRequest(BaseModel):
    employee_email: str
    data: Any
    query: str
    namespace: Literal["legal", "hr", "engineering", "coding", "support"]
    function: str

# ---- Ingestion contracts ----

class SourceItem(BaseModel):
    path:str
    type: Literal["pdf","url", "markdown"]

class IngestionRequest(BaseModel):
    namespace: Literal["legal", "hr", "engineering", "coding", "support"]
    source: list[SourceItem]


class IngestionResponse(BaseModel):
    chunks_created: int
    namespace: str
    status: Literal["success", "partial", "failed"]


# ---- Agent output contract (used by ALL domain agents) ----

class AgentAnswer(BaseModel):
    domain: str
    answer: str
    sources: list[str]
    confidence: float
    context: list[str]
    requires_human_review: bool = False
    generated_at: datetime = Field(default_factory=datetime.utcnow)

class AgentAnswerLLM(BaseModel):
    confidence: float
    requires_human_review: bool = False


class PausedForReviewResponse(BaseModel):
    status: Literal["paused_for_review"] = "paused_for_review"
    review_payload: Any
    thread_id: str

class RetrievalPlan(BaseModel):
    needs_retrieval: bool = Field(description="Choose whetehr a particular query need a retrieal or not")
    source: Literal["none","sql","vector"] = Field(description="select the retrieval method")
    reason: str = Field(description="describe reason to choose this retrieval method")

class RetrievalAssessment(BaseModel):
    relevant: bool = Field(description="Whether the retrieved text contains enough evidence to answer the user's question.")
    reason: str = Field(description="Brief explanation of the evidence quality.")
    can_be_answered_by_tool: bool = Field(
        description="Whether one of the supplied live tools directly supports the user's request."
    )

class RewrittenQuery(BaseModel):
    search_query: str = Field(description="A concise semantic-search query preserving important names, IDs, dates, and constraints.")

class SQLQuerySelection(BaseModel):
    query_name: Literal["leave_balance","CTC_data","get_ticket_status","contract_tracking","deployment_status"]
    reason: str = Field(description="give reason to choose the particulat method for the query")
    params: dict[str, str] = Field(
        default_factory=dict,
        description='''Key-value parameters required by the chosen function, extracted from the user's question. Empty if the function needs none. Never invent values not present in the question.
        
        '''
    )

class SQLResponse(BaseModel):
    source: str
    content: str

class SQLRetrievalResponse(BaseModel):
    results: list[SQLResponse]
    namespace: str
    query_time_ms: float
# ---- Evaluation contracts ----

class EvalRequest(BaseModel):
    query: str
    answer: str
    retrieved_context: list[str]
    confidence: float
    ground_truth: str | None = None


class EvalResponse(BaseModel):
    faithfulness: float
    answer_relevancy: float
    flagged: bool

# ---- Orchesstrator contratcs -----

class OrchestratorRequest(BaseModel):
    query: str
    allowed_namespace: list[str]
    thread_id: Optional[str] = None
    employee_email:str

class RevisedAnswer(BaseModel):
    revised_answer: str
    approved: bool
    edited: bool

class RequestResume(BaseModel):
    human_response: RevisedAnswer
    thread_id: str

