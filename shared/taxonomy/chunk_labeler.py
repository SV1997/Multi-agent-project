"""Chunk-level labels: which of a document's categories is ONE chunk really about?

Why this file exists: policy_taxonomy.yaml lists categories per DOCUMENT, so every chunk of the HR handbook carried
all 16 labels and a category filter could not tell a leave chunk from a salary chunk (measured: a leave-only filter
matched 84 of the 92 HR chunks). Here a language model reads one chunk and chooses from its document's own list.

Three safety rules keep this from ever being worse than the document-level labels it replaces:
  1. the model may only choose from the categories the YAML lists for that document; anything else is thrown away;
  2. if the model fails or chooses nothing valid, the chunk keeps the document's whole list (the old behaviour);
  3. a document with a single category needs no model at all.

The model is passed in, never created here, so ingestion, the relabelling script and the tests can each supply their
own (the tests use a fake). It only has to offer .batch(list_of_messages, config=..., return_exceptions=True), which
every LangChain chat model with structured output does.
"""
from __future__ import annotations

import logging

from pydantic import BaseModel

logger = logging.getLogger(__name__)

MAX_PARALLEL = 8          # how many chunks are sent to the model at the same time


class ChunkLabels(BaseModel):
    """The only thing the model may answer: the names of the categories the chunk is about."""
    categories: list[str]


def build_openai_labeler(model: str, api_key: str | None):
    """The labelling model, as ingestion and scripts/label_documents.py both use it: one place, so they can't drift apart.

    Same style as the contract extraction (extraction/contracts.py): temperature 0 so the same chunk gets the same
    labels, and the answer is forced into the ChunkLabels shape. Imported here, not at the top, so tests and
    services that never label chunks don't need the OpenAI package.
    """
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(model=model, api_key=api_key, temperature=0).with_structured_output(ChunkLabels)


def build_prompt(taxonomy, domain: str, candidates: list[str]) -> str:
    """Tells the model what the categories mean. Only this document's categories are listed, so no other can be picked."""
    known = taxonomy.categories.get(domain, {})
    lines = [f"- {name}: {known[name].description if name in known else ''}" for name in candidates]
    return (f"You label one chunk of a {domain} policy document. Choose the categories below that the chunk is "
            "actually about: usually 1 or 2, at most 3. Choose only categories whose topic the chunk's own text "
            "covers. Choose non_content (when it is offered) ONLY when the chunk is navigation or a list of citations: "
            "a menu, a table of contents, a list of links, or reference lines (a source name, an archive note, a "
            "retrieval date). A fragment of ordinary policy text is NEVER non_content, even a short one or one that "
            "starts or ends in the middle of a sentence: choose the closest topic instead. "
            "Answer with the category names exactly as written.\n\nCategories:\n" + "\n".join(lines))


def only_candidates(answer, candidates: list[str]) -> list[str]:
    """What the model chose, minus anything that is not a candidate, in the document's own order and each once.

    The document's order (not the model's) keeps the result stable, so labelling the same chunk twice gives the same list.
    """
    chosen = set(getattr(answer, "categories", None) or [])
    return [name for name in candidates if name in chosen]


def label_chunks(llm, taxonomy, domain: str, candidates, texts: list[str], max_parallel: int = MAX_PARALLEL) -> list[list[str]]:
    """One list of categories per text, same order as `texts`. Never raises: a failed chunk keeps all `candidates`."""
    candidates = list(candidates)
    keep_all = [list(candidates) for _ in texts]
    if llm is None or len(candidates) < 2 or not texts:        # rule 3 (and: no model configured)
        return keep_all

    system = build_prompt(taxonomy, domain, candidates)
    messages = [[("system", system), ("human", text)] for text in texts]
    try:
        answers = llm.batch(messages, config={"max_concurrency": max_parallel}, return_exceptions=True)
    except Exception:
        logger.exception("Chunk labelling failed; every chunk keeps its document's categories")
        return keep_all

    labels, fell_back = [], 0
    for answer, all_of_them in zip(answers, keep_all):
        chosen = [] if isinstance(answer, Exception) else only_candidates(answer, candidates)
        if not chosen:                                          # rule 2: a failed or empty answer is not trusted
            fell_back += 1
            chosen = all_of_them
        labels.append(chosen)
    if fell_back:
        logger.warning("%d of %d chunks kept their document's categories (model failed or chose nothing valid)",
                       fell_back, len(texts))
    return labels
