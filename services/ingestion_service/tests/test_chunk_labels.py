"""Chunk-level labels at ingestion. Run from services/ingestion_service:  python -m pytest tests/test_chunk_labels.py

Only tag_chunks (the step that writes labels onto the chunks of one document) is run; the language model is a fake.
"""
import os
import sys
import types

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))
fake_emb = types.ModuleType("shared.embeddings.embeddings")
fake_emb.embeddings = object()
sys.modules.setdefault("shared.embeddings.embeddings", fake_emb)

from langchain_core.documents import Document  # noqa: E402
from shared.taxonomy.chunk_labeler import ChunkLabels  # noqa: E402
from shared.taxonomy.taxonomy import parse_taxonomy  # noqa: E402
from app.pinecone import upsert as up  # noqa: E402

TAX = parse_taxonomy({
    "hr": {
        "categories": {
            "earned_leave": {"description": "Earned leave", "parents": []},
            "salary_payment": {"description": "Salary payment", "parents": []},
        },
        "documents": {"handbook.pdf": {"title": "HR Handbook", "categories": ["earned_leave", "salary_payment"]}},
    }
})


class FakeModel:
    def __init__(self, answers):
        self.answers = answers

    def batch(self, messages, config=None, return_exceptions=False):
        return [self.answers[chunk[1][1]] for chunk in messages]


def chunks():
    texts = ["Earned leave accrues monthly.", "Salary is paid on the last working day."]
    return {f"id{i}": Document(page_content=t, metadata={"source": "/tmp/tmpabc.pdf", "file_name": "handbook.pdf"})
            for i, t in enumerate(texts)}


def test_each_chunk_of_one_document_gets_its_own_categories():
    model = FakeModel({"Earned leave accrues monthly.": ChunkLabels(categories=["earned_leave"]),
                       "Salary is paid on the last working day.": ChunkLabels(categories=["salary_payment"])})
    docs = chunks()
    up.tag_chunks(docs, "hr", TAX, model)
    assert docs["id0"].metadata["categories"] == ["earned_leave"]
    assert docs["id1"].metadata["categories"] == ["salary_payment"]
    assert docs["id0"].metadata["title"] == "HR Handbook"          # the other labels are unchanged


def test_without_a_labeler_every_chunk_still_gets_the_whole_document_list():
    docs = chunks()
    up.tag_chunks(docs, "hr", TAX)
    assert docs["id0"].metadata["categories"] == ["earned_leave", "salary_payment"]
    assert docs["id1"].metadata["categories"] == ["earned_leave", "salary_payment"]


def test_a_labeler_that_fails_leaves_the_old_behaviour():
    class Broken:
        def batch(self, *args, **kwargs):
            raise RuntimeError("no network")

    docs = chunks()
    up.tag_chunks(docs, "hr", TAX, Broken())
    assert docs["id0"].metadata["categories"] == ["earned_leave", "salary_payment"]
