"""Compare recall@5 with re-ranking off vs on over a labelled question file.

Copy eval/rerank_questions.template.json to eval/rerank_questions.json, fill it in, then run from
services/retrieval-service (needs PINECONE/OPENAI/DATABASE_URL env and `pip install sentence-transformers`):
    python scripts/compare_rerank.py [eval/rerank_questions.json]

recall@5 per question = share of its relevant_substrings found in the 5 returned chunks (case-insensitive).
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.core import config  # noqa: E402
from app.pinecone.namespace_router import query_namespace  # noqa: E402
from shared.contracts.schema import RetrievalQuery  # noqa: E402

K = 5


def recall_at_k(contents: list[str], relevant: list[str]) -> float:
    text = "\n".join(contents).lower()
    return sum(r.lower() in text for r in relevant) / len(relevant) if relevant else 0.0


async def evaluate(questions: list[dict], rerank_on: bool) -> float:
    config.RERANK_ENABLED = rerank_on
    scores = []
    for q in questions:
        res = await query_namespace(RetrievalQuery(query=q["question"], namespace=q["namespace"], top_k=K))
        scores.append(recall_at_k([c.content for c in res.results], q["relevant_substrings"]))
    return sum(scores) / len(scores)


async def main(path: str) -> None:
    questions = json.load(open(path, encoding="utf-8"))
    off = await evaluate(questions, False)
    on = await evaluate(questions, True)
    print(f"questions={len(questions)}  recall@{K}: rerank OFF={off:.3f}  rerank ON={on:.3f}  delta={on - off:+.3f}")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "../eval/rerank_questions.json")))
