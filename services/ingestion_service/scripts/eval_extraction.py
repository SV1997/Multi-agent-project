"""Per-field accuracy of contract extraction against a labelled JSON file.

Copy eval/extraction_labels.template.json to eval/extraction_labels.json, fill it in, then run from
services/ingestion_service (needs OPENAI_API_KEY):
    python scripts/eval_extraction.py [eval/extraction_labels.json]

A field is correct when the extracted value equals the label (text ignores case/extra spaces, numbers
are compared to 2 decimals). A missing extracted value counts as wrong.
"""
import json
import os
import sys
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))
from app.extraction.contracts import FIELDS, ContractExtraction, document_text, extract_contract  # noqa: E402
from app.loader.encoder import load_document  # noqa: E402


def field_matches(field: str, expected: Any, predicted: Any) -> bool:
    if predicted is None:
        return False
    if field == "value":
        return round(float(expected), 2) == round(float(predicted), 2)
    if field == "auto_renews":
        return bool(expected) == bool(predicted)
    return " ".join(str(expected).split()).casefold() == " ".join(str(predicted).split()).casefold()


def as_dict(ex: ContractExtraction) -> dict[str, Any]:
    return {
        "counterparty": ex.counterparty,
        "expiry_date": ex.expiry_date.isoformat() if ex.expiry_date else None,
        "value": float(ex.value) if ex.value is not None else None,
        "currency": ex.currency,
        "auto_renews": ex.auto_renews,
    }


def field_accuracy(pairs: list[tuple[dict, dict]]) -> dict[str, float]:
    """pairs = [(expected, predicted), ...] -> {field: share correct}."""
    return {f: sum(field_matches(f, e[f], p.get(f)) for e, p in pairs) / len(pairs) for f in FIELDS if pairs}


def main(path: str) -> None:
    labels = json.load(open(path, encoding="utf-8"))
    pairs, flagged = [], 0
    for item in labels:
        ex = extract_contract(document_text(load_document(item["path"], item["type"])))
        flagged += ex.needs_review
        pairs.append((item["expected"], as_dict(ex)))
    print(f"documents={len(pairs)}  flagged needs_review={flagged}")
    for field, acc in field_accuracy(pairs).items():
        print(f"{field:14s} {acc:.1%}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "../eval/extraction_labels.json"))
