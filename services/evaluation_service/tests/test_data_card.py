"""Feature 7: the data card template exists and has every required field.
Run from services/evaluation_service: python -m pytest tests/test_data_card.py"""
import os

CARD = os.path.join(os.path.dirname(__file__), "../../../docs/data_card.md")
FIELDS = [
    "Document sources (real vs synthetic)",
    "Who wrote the questions",
    "Dev / test split",
    "Number of no-answer questions",
    "Number of conflict questions",
]


def test_data_card_has_all_fields():
    text = open(CARD, encoding="utf-8").read()
    assert all(f in text for f in FIELDS)
