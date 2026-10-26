"""The metadata fields a chunk carries once it has been categorized.

Why this file exists: three places need to agree on what a "tagged" chunk looks like - the backfill script
(chunks already stored), the ingestion service (new chunks) and retrieval (the filter it builds). If each
one worked out the fields on its own, a small difference (say, how "is_content" is decided) would make some
chunks invisible to a filtered search. So the rules live here, once.

Problem it solves: turn the taxonomy's answer for a chunk into the exact fields stored in Pinecone and in the
BM25 index, and work out the smallest change needed when a chunk already has some of them (so re-running a
backfill does nothing for chunks that are already right).

Fields:
    categories      list of category names (what the search filter matches on)
    is_content      False only when the chunk is exactly ["non_content"] (menus, reference lists of web pages)
    title           the document title from the taxonomy, when it has one
    original_title  the title the file/page had before the taxonomy title replaced it (kept, never lost)
"""
from .taxonomy import Taxonomy

NON_CONTENT = "non_content"


def tag_fields(tax: Taxonomy, domain: str, source: str, chunk_id: str | None = None,
               file_name: str | None = None) -> dict:
    """What this chunk should carry, according to the taxonomy."""
    categories = list(tax.for_chunk(domain, source, chunk_id, file_name))
    fields = {
        "categories": categories,
        "is_content": categories != [NON_CONTENT],
    }
    title = tax.title_for(domain, source, chunk_id, file_name)
    if title:
        fields["title"] = title
    return fields


def fields_to_set(target: dict, existing: dict) -> dict:
    """The fields that must be written so that `existing` metadata matches `target`. Empty = already correct.

    When the taxonomy title replaces a different title, the old one is saved once under "original_title".
    """
    changes = {}
    for key in ("categories", "is_content"):
        if existing.get(key) != target[key]:
            changes[key] = target[key]

    new_title = target.get("title")
    if new_title and existing.get("title") != new_title:
        changes["title"] = new_title
        old_title = existing.get("title")
        if old_title and "original_title" not in existing:
            changes["original_title"] = old_title
    return changes
