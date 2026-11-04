"""The messages sent to the query rewriter. Kept apart from the graph so the prompt can be tested without a model.

The rewriter runs only after a search came back without enough evidence. It is told that, shown what came back,
what was missing and which queries already failed, so it can aim at the gap and not just rephrase the question.
"""
from langchain_core.messages import HumanMessage, SystemMessage

PASSAGE_CHARS = 200     # per passage: enough to see the topic, short because the Groq token budget is small
MAX_PASSAGES = 5

SYSTEM = (
    "You are the query-rewriting step of a retrieval-augmented assistant that answers questions from a company's "
    "policy documents.\n"
    "A search for the user's question has just come back without enough evidence to answer it. You are given the "
    "question, the conversation so far, the queries already tried, a short preview of the passages the last search "
    "returned, and the reason they were not enough. Write ONE new search query that is likely to find the missing "
    "information.\n"
    "Rules:\n"
    "- Aim at what is missing, not at what was already found. If the passages were on the wrong topic, move toward "
    "the right topic; if they were on the right topic but lacked the detail, ask for that detail.\n"
    "- Use the words a policy document would use (formal terms and synonyms, for example 'leave entitlement' for "
    "'days off'), not the user's casual wording.\n"
    "- Do not repeat or lightly reword a query that was already tried.\n"
    "- Keep every named entity, employee ID, date and constraint from the question. If the question refers back to "
    "the conversation ('it', 'that policy', 'the second one'), replace the reference with what it points to.\n"
    "- Return only the search query, as a short phrase or sentence. Do not answer the question."
)


def passage_digest(chunks: list[dict]) -> str:
    """One line per returned passage: its source and the start of its text. 'none' when the search returned nothing."""
    lines = []
    for index, chunk in enumerate((chunks or [])[:MAX_PASSAGES], 1):
        text = " ".join(str(chunk.get("content", "")).split())[:PASSAGE_CHARS]
        lines.append(f"{index}. [{chunk.get('source', 'unknown')}] {text}")
    return "\n".join(lines) or "none (the search returned no passages)"


def rewrite_messages(state: dict, conversation: str) -> list:
    tried = state.get("tried_queries") or [state.get("search_query") or state.get("original_query") or ""]
    human = (
        f"Conversation so far:\n{conversation}\n\n"
        f"User's question: {state.get('original_query', '')}\n\n"
        "Queries already tried (none of them found enough):\n" + "\n".join(f"- {q}" for q in tried if q) + "\n\n"
        f"What the last search returned:\n{passage_digest(state.get('retrieved_context'))}\n\n"
        f"Why that was not enough: {state.get('retrieval_assessment') or 'not given'}\n"
        f"What is missing: {state.get('retrieval_missing') or 'not given'}"
    )
    return [SystemMessage(content=SYSTEM), HumanMessage(content=human)]
