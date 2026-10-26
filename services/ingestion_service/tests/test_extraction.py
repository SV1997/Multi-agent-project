"""Contract extraction: validation in code, review flags, delete-and-rewrite storage.
Run from services/ingestion_service: python -m pytest tests/test_extraction.py   (no network, fake LLM + fake DB)"""
import asyncio
import json
import os
import sys
from contextlib import asynccontextmanager
from datetime import date
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))
from app.extraction import contracts as c  # noqa: E402

TEXT = ("This agreement with Acme Corp expires on 31 March 2027. Total fees are USD 120,000. "
        "The agreement renews automatically for one year.")


def raw(**over) -> c.RawContractExtraction:
    base = dict(
        counterparty=c.StrField(value="Acme Corp", source_quote="agreement with Acme Corp", confidence=0.95),
        expiry_date=c.StrField(value="2027-03-31", source_quote="expires on 31 March 2027", confidence=0.9),
        value=c.NumField(value=120000, source_quote="USD 120,000", confidence=0.9),
        currency=c.StrField(value="usd", source_quote="USD 120,000", confidence=0.9),
        auto_renews=c.BoolField(value=True, source_quote="renews automatically", confidence=0.8),
    )
    base.update(over)
    return c.RawContractExtraction(**base)


def test_clean_extraction_is_typed_and_not_flagged():
    ex = c.validate_extraction(raw(), TEXT)
    assert ex.expiry_date == date(2027, 3, 31) and ex.value == Decimal("120000")
    assert ex.currency == "USD" and ex.auto_renews is True and ex.needs_review is False
    assert ex.details["expiry_date"]["source_quote"] == "expires on 31 March 2027"


def test_missing_field_needs_review():
    ex = c.validate_extraction(raw(currency=c.StrField(value=None, source_quote=None, confidence=0)), TEXT)
    assert ex.needs_review and "missing: currency" in ex.review_reasons and ex.currency is None


def test_invalid_date_and_negative_value_rejected():
    ex = c.validate_extraction(raw(
        expiry_date=c.StrField(value="31/03/2027", source_quote="expires on 31 March 2027", confidence=0.9),
        value=c.NumField(value=-5, source_quote="USD 120,000", confidence=0.9)), TEXT)
    assert ex.expiry_date is None and ex.value is None
    assert any("invalid expiry_date" in r for r in ex.review_reasons)
    assert any("invalid value" in r for r in ex.review_reasons)


def test_low_confidence_flagged():
    ex = c.validate_extraction(raw(counterparty=c.StrField(value="Acme Corp", source_quote="agreement with Acme Corp", confidence=0.3)), TEXT)
    assert ex.needs_review and any("low confidence: counterparty" in r for r in ex.review_reasons)


def test_invented_quote_flagged():
    ex = c.validate_extraction(raw(auto_renews=c.BoolField(value=False, source_quote="never renews", confidence=0.99)), TEXT)
    assert ex.needs_review and any("source quote not found" in r for r in ex.review_reasons)


def test_extract_contract_uses_injected_llm():
    class FakeLLM:
        def invoke(self, messages):
            return raw()
    assert c.extract_contract(TEXT, llm=FakeLLM()).needs_review is False


class FakeConn:
    def __init__(self):
        self.calls = []

    @asynccontextmanager
    async def transaction(self):
        yield

    async def execute(self, sql, *args):
        self.calls.append((sql.split()[0], args))


def test_reingest_deletes_then_rewrites_rows():
    conn = FakeConn()
    ex = c.validate_extraction(raw(), TEXT)
    asyncio.run(c.save_extraction(conn, "doc1", 2, "legal", "contract.pdf", ex, "contract"))
    assert [k for k, _ in conn.calls] == ["DELETE", "INSERT"]
    assert conn.calls[0][1] == ("doc1",)  # all older versions of this doc go
    insert_args = conn.calls[1][1]
    assert insert_args[:2] == ("doc1", 2) and insert_args[3] == "contract"  # document_type is stored
    assert json.loads(insert_args[-1])["value"]["confidence"] == 0.9


def test_field_accuracy_script():
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../scripts"))
    from eval_extraction import field_accuracy
    exp = {"counterparty": "Acme Corp", "expiry_date": "2027-03-31", "value": 120000, "currency": "USD", "auto_renews": True}
    good = {"counterparty": "acme  corp", "expiry_date": "2027-03-31", "value": 120000.0, "currency": "USD", "auto_renews": True}
    bad = dict(good, expiry_date="2027-04-01", currency=None)
    acc = field_accuracy([(exp, good), (exp, bad)])
    assert acc["counterparty"] == 1.0 and acc["expiry_date"] == 0.5 and acc["currency"] == 0.5


# ---- document_type gate in the ingest route ----
import pytest  # noqa: E402
from langchain_core.documents import Document  # noqa: E402


def _run_ingest(monkeypatch, document_type, flag, namespace="legal"):
    from app.api import route

    calls = []

    async def fake_extract(docs, doc_id, version, path):
        calls.append(doc_id)
        return []

    async def fake_load(_):
        return None

    async def fake_save(ns, data):
        pass

    monkeypatch.setattr(route, "extract_and_store", fake_extract)
    monkeypatch.setattr(route, "CONTRACT_EXTRACTION_ENABLED", flag)
    monkeypatch.setattr(route, "load_bm25_index", fake_load)
    monkeypatch.setattr(route, "save_bm25_index", fake_save)
    monkeypatch.setattr(route, "load_document", lambda source, source_type: [Document(page_content="Some legal text.", metadata={})])
    monkeypatch.setattr(route, "upsert_document", lambda chunks, ns, doc_id, eff, **_: len(chunks))
    item = {"path": "a.pdf", "type": "pdf"}
    if document_type is not None:
        item["document_type"] = document_type
    res = asyncio.run(route.ingest(route.IngestionRequest(namespace=namespace, source=[item])))
    return calls, res


@pytest.mark.parametrize("document_type", [None, "regulation", "policy"])
def test_extraction_skipped_for_non_contracts_without_warning(monkeypatch, document_type):
    calls, res = _run_ingest(monkeypatch, document_type, flag=True)
    assert calls == [] and not any('extraction' in w for w in res.warnings)


def test_extraction_runs_for_contract_when_flag_on(monkeypatch):
    calls, _ = _run_ingest(monkeypatch, "contract", flag=True)
    assert len(calls) == 1


def test_extraction_skipped_for_contract_when_flag_off(monkeypatch):
    calls, res = _run_ingest(monkeypatch, "contract", flag=False)
    assert calls == [] and not any('extraction' in w for w in res.warnings)


def test_extraction_skipped_outside_legal_namespace(monkeypatch):
    calls, _ = _run_ingest(monkeypatch, "contract", flag=True, namespace="hr")
    assert calls == []


def test_invalid_document_type_rejected():
    from pydantic import ValidationError
    from shared.contracts.schema import IngestionRequest
    with pytest.raises(ValidationError):
        IngestionRequest(namespace="legal", source=[{"path": "a.pdf", "type": "pdf", "document_type": "memo"}])
