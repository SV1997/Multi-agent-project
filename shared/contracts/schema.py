# shared/schemas/contracts.py
"""
Shared Pydantic contracts used across all services (orchestrator, retrieval-service,
ingestion-service, tool-service, evaluation-service). Node.js services use the
equivalent Zod schema (shared/schemas/contracts.ts) to keep wire format in sync.
"""

from pydantic import BaseModel, Field
from typing import Any, Literal
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
    requires_human_review: bool = False
    generated_at: datetime = Field(default_factory=datetime.utcnow)

class AgentAnswerLLM(BaseModel):
    answer: str
    sources: list[str]
    confidence: float
    requires_human_review: bool = False


class PausedForReviewResponse(BaseModel):
    status: Literal["paused_for_review"] = "paused_for_review"
    review_payload: Any
    thread_id: str

# ---- Evaluation contracts ----

class EvalRequest(BaseModel):
    query: str
    answer: str
    retrieved_context: list[str]
    ground_truth: str | None = None


class EvalResponse(BaseModel):
    faithfulness: float
    answer_relevancy: float
    context_precision: float
    context_recall: float

# ---- Orchesstrator contratcs -----

class OrchestratorRequest(BaseModel):
    query: str
    # user_id: str

class RevisedAnswer(BaseModel):
    revised_answer: str
    approved: bool
    edited: bool

class RequestResume(BaseModel):
    human_response: RevisedAnswer
    thread_id: str

