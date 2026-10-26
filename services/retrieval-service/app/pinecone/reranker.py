import logging
import sys
import os
from functools import lru_cache
from typing import Callable
sys.path.append(os.path.join(os.path.dirname(__file__), "../../../.."))
from shared.contracts.schema import RetrievedChunk
from ..core import config

logger = logging.getLogger(__name__)

Scorer = Callable[[list[tuple[str, str]]], list[float]]


@lru_cache(maxsize=1)
def _load_scorer() -> Scorer:
    # Imported lazily: sentence-transformers (and torch) is an optional dependency, only needed when RERANK_ENABLED=true.
    from sentence_transformers import CrossEncoder
    model = CrossEncoder(config.RERANK_MODEL)
    return lambda pairs: [float(s) for s in model.predict(pairs)]


def rerank(query: str, chunks: list[RetrievedChunk], top_n: int, scorer: Scorer | None = None) -> list[RetrievedChunk]:
    """Re-order fused candidates with a cross-encoder and keep top_n. On any failure, keeps the fused order."""
    if len(chunks) <= 1:
        return chunks[:top_n]
    try:
        scores = (scorer or _load_scorer())([(query, c.content) for c in chunks])
    except Exception:
        logger.exception("Re-ranking failed; falling back to fused (RRF) order.")
        return chunks[:top_n]
    ranked = sorted(zip(chunks, scores), key=lambda x: x[1], reverse=True)
    return [c.model_copy(update={"score": s}) for c, s in ranked[:top_n]]
