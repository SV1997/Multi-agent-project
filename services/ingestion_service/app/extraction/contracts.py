import json
import math
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Optional
from pydantic import BaseModel, Field
from langchain_core.documents import Document
from ..core.config import (
    EXTRACTION_MAX_CHARS,
    EXTRACTION_MIN_CONFIDENCE,
    EXTRACTION_MODEL,
    OPENAI_API_KEY,
)

FIELDS = ("counterparty", "expiry_date", "value", "currency", "auto_renews")


# ---- What the LLM returns (every field required so the JSON schema is strict-compatible) ----

class StrField(BaseModel):
    value: Optional[str]
    source_quote: Optional[str] = Field(description="Exact words copied from the contract that support the value")
    confidence: float = Field(description="0.0 to 1.0")


class NumField(BaseModel):
    value: Optional[float]
    source_quote: Optional[str]
    confidence: float


class BoolField(BaseModel):
    value: Optional[bool]
    source_quote: Optional[str]
    confidence: float


class RawContractExtraction(BaseModel):
    counterparty: StrField = Field(description="The other party to the contract (not our own company)")
    expiry_date: StrField = Field(description="Contract end/expiry date as ISO YYYY-MM-DD")
    value: NumField = Field(description="Total contract value as a plain number, no currency symbol")
    currency: StrField = Field(description="ISO 4217 code such as USD, EUR, INR")
    auto_renews: BoolField = Field(description="True if the contract renews automatically")


# ---- What we keep after validation ----

class ContractExtraction(BaseModel):
    counterparty: Optional[str] = None
    expiry_date: Optional[date] = None
    value: Optional[Decimal] = None
    currency: Optional[str] = None
    auto_renews: Optional[bool] = None
    details: dict[str, dict[str, Any]] = Field(default_factory=dict)  # per field: source_quote, confidence
    needs_review: bool = False
    review_reasons: list[str] = Field(default_factory=list)


EXTRACTION_PROMPT = (
    "Extract the following fields from the contract text: counterparty, expiry_date (ISO YYYY-MM-DD), "
    "value (number), currency (ISO code), auto_renews (boolean). For every field give the exact words "
    "from the contract that support it as source_quote, and a confidence between 0 and 1. "
    "If a field is not stated, set value and source_quote to null and confidence to 0. Never guess."
)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _parse(name: str, value: Any) -> Any:
    """Convert to the stored type or raise ValueError."""
    if name == "counterparty":
        if not isinstance(value, str) or not value.strip():
            raise ValueError("empty")
        return value.strip()
    if name == "expiry_date":
        return date.fromisoformat(str(value))
    if name == "value":
        number = Decimal(str(value))
        if not number.is_finite() or number < 0:
            raise ValueError("negative or non-finite")
        return number
    if name == "currency":
        code = str(value).strip().upper()
        if not re.fullmatch(r"[A-Z]{3}", code):
            raise ValueError("not a 3-letter code")
        return code
    if not isinstance(value, bool):
        raise ValueError("not a boolean")
    return value


def validate_extraction(raw: RawContractExtraction, text: str, min_confidence: float = EXTRACTION_MIN_CONFIDENCE) -> ContractExtraction:
    """Type/date checks in code. Missing, invalid, unsupported or low-confidence fields set needs_review."""
    out = ContractExtraction()
    haystack = _norm(text)
    for name in FIELDS:
        field = getattr(raw, name)
        conf = field.confidence if isinstance(field.confidence, (int, float)) and not math.isnan(field.confidence) else 0.0
        conf = min(max(float(conf), 0.0), 1.0)
        out.details[name] = {"source_quote": field.source_quote, "confidence": conf}
        if field.value is None:
            out.review_reasons.append(f"missing: {name}")
            continue
        try:
            parsed = _parse(name, field.value)
        except (ValueError, InvalidOperation, TypeError):
            out.review_reasons.append(f"invalid {name}: {field.value!r}")
            continue
        setattr(out, name, parsed)
        if conf < min_confidence:
            out.review_reasons.append(f"low confidence: {name} ({conf:.2f})")
        if not field.source_quote or _norm(field.source_quote) not in haystack:
            out.review_reasons.append(f"source quote not found in document: {name}")
    out.needs_review = bool(out.review_reasons)
    return out


def document_text(docs: list[Document]) -> str:
    return "\n\n".join(d.page_content for d in docs)[:EXTRACTION_MAX_CHARS]


def extract_contract(text: str, llm: Any = None) -> ContractExtraction:
    """One LLM call with a JSON schema, then code-side validation. `llm` is injectable for tests."""
    if llm is None:
        from langchain_openai import ChatOpenAI
        llm = ChatOpenAI(model=EXTRACTION_MODEL, api_key=OPENAI_API_KEY, temperature=0).with_structured_output(RawContractExtraction)
    raw = llm.invoke([("system", EXTRACTION_PROMPT), ("human", text)])
    return validate_extraction(raw, text)


async def save_extraction(conn, doc_id: str, version: int, namespace: str, source: str, ex: ContractExtraction, document_type: str) -> None:
    """Delete every earlier row of this document, then write the new one (atomic)."""
    async with conn.transaction():
        await conn.execute('DELETE FROM doc_extractions WHERE doc_id = $1', doc_id)
        await conn.execute(
            'INSERT INTO doc_extractions (doc_id, version, namespace, document_type, source, counterparty, expiry_date, value, '
            'currency, auto_renews, needs_review, review_reasons, details) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13::jsonb)',
            doc_id, version, namespace, document_type, source, ex.counterparty, ex.expiry_date, ex.value, ex.currency,
            ex.auto_renews, ex.needs_review, ex.review_reasons, json.dumps(ex.details),
        )
