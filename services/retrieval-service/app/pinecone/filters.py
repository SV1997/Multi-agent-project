"""How a localized search narrows what it looks at.

Why this file exists: with LOCALIZE on, a search must only use chunks that are real content and, when the
request names categories, chunks in those categories. The vector search (Pinecone) and the keyword search
(BM25) store the labels in different shapes, so each needs its own test - but both must mean the same thing.
Keeping the two rules side by side here, as small pure functions, makes that easy to see and to test.

Problem it solves: stop a menu or reference list from being cited as policy, and stop a rule from one category
being borrowed to answer a question about another.

The labels (categories, is_content, ...) are written on chunks by scripts/backfill.py and by ingestion
(see shared/taxonomy/tagging.py). A chunk that has no labels is NOT returned by a localized search - the same
way Pinecone treats a missing field - so a chunk ingested without labels is only found with LOCALIZE=off.
"""

CHUNK_TAG_FIELDS = ("categories", "is_content", "title", "file_name")

# The namespaces the taxonomy covers (shared/taxonomy DOMAINS; a test keeps the two lists equal). Chunks in any
# other namespace (for example "coding") carry no labels, so a filter there would return nothing at all.
LOCALIZED_NAMESPACES = ("legal", "hr", "engineering", "finance", "support")


def pinecone_filter(categories: list[str] | None) -> dict:
    """Pinecone metadata filter: content chunks only, and in one of `categories` when any are given.

    "categories" is a list on each chunk; $in matches a chunk when ANY of its categories is in the list.
    No categories (None or empty) means every category, so only the content rule applies.
    """
    content_only = {"is_content": {"$eq": True}}
    if not categories:
        return content_only
    return {"$and": [{"categories": {"$in": list(categories)}}, content_only]}


def keyword_chunk_allowed(chunk, categories: list[str] | None) -> bool:
    """The same rule as pinecone_filter, for one BM25 chunk (a dict with the labels stored next to the text)."""
    if not isinstance(chunk, dict):       # an old plain-text chunk has no labels at all
        return False
    if chunk.get("is_content") is not True:
        return False
    if not categories:
        return True
    return bool(set(chunk.get("categories") or ()) & set(categories))


def chunk_tags(chunk) -> dict:
    """The labels of a keyword-index chunk, to show next to its text in the search result."""
    if not isinstance(chunk, dict):
        return {}
    return {key: chunk[key] for key in CHUNK_TAG_FIELDS if key in chunk}
