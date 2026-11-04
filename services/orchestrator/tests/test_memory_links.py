"""Memory links: a memory that corrects an older one hides it, and its text is shown as "(earlier: ...)".

Run from services/orchestrator:  python -m pytest tests/test_memory_links.py
Plain dicts stand in for database rows and a fake async function for the database; no model is called.
The dummy keys below are only so that importing conversation_memory (which builds its model client) works on a clean checkout.
"""
import asyncio
import os
import sys
from datetime import datetime

for name in ("OPENAI_API_KEY", "GROQ_API_KEY"):
    os.environ.setdefault(name, "test")
os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost/db")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))
from app.graph.conversation_memory import (  # noqa: E402
    attach_earlier, current_memories, render_memories, valid_links, with_linked)


def row(id, text, day, linked=()):
    return {"id": id, "text": text, "created_at": datetime(2026, 11, day), "linked_ids": list(linked)}


OLD = row("a", "User filed a medical claim for 15,000", 1)
FIX = row("b", "User corrected the medical claim amount from 15,000 to 12,500", 2, ["a"])
LEAVE = row("c", "User applied for leave from 12 Dec to 19 Dec", 3)


# a) current_memories

def test_a_memory_that_a_newer_one_links_to_is_dropped_and_order_is_kept():
    assert current_memories([OLD, FIX, LEAVE]) == [FIX, LEAVE]


def test_without_links_everything_is_current():
    assert current_memories([OLD, LEAVE]) == [OLD, LEAVE]


def test_a_link_to_a_memory_that_is_not_in_the_list_changes_nothing():
    assert current_memories([FIX, LEAVE]) == [FIX, LEAVE]


def test_a_link_that_points_forward_in_time_does_not_hide_anything():
    backwards = row("a", "older", 1, ["b"])               # claims to replace a NEWER memory
    assert current_memories([backwards, row("b", "newer", 2)]) == [backwards, row("b", "newer", 2)]


def test_ids_compare_as_text_so_uuid_objects_and_strings_mix():
    import uuid
    old_id = uuid.uuid4()
    old = row(old_id, "old", 1)
    new = row("n", "new", 2, [str(old_id)])
    assert current_memories([old, new]) == [new]


# b) with_linked: pulls in memories connected by a link, in both directions

def fetcher(*stored):
    """Fake database: rows whose id is wanted, or that link to one of the recalled ids."""
    calls = []

    async def fetch(ids, recalled):
        calls.append((list(ids), list(recalled)))
        return [dict(r) for r in stored if r["id"] in ids or set(r["linked_ids"]) & set(recalled)]
    fetch.calls = calls
    return fetch


def test_the_older_memory_a_recalled_one_links_to_is_added():
    out = asyncio.run(with_linked(fetcher(OLD), [FIX, LEAVE]))
    assert [r["id"] for r in out] == ["b", "c", "a"]


def test_a_newer_correction_that_was_not_recalled_is_added_so_the_old_one_is_hidden():
    out = asyncio.run(with_linked(fetcher(OLD, FIX), [OLD]))          # only the stale memory was recalled
    assert [r["id"] for r in out] == ["a", "b"]
    assert current_memories(out) == [FIX]


def test_a_chain_of_corrections_is_followed():
    third = row("d", "User corrected the medical claim amount from 12,500 to 13,000", 4, ["b"])
    out = asyncio.run(with_linked(fetcher(OLD, FIX, third), [OLD]))
    assert [r["id"] for r in out] == ["a", "b", "d"]
    assert current_memories(out) == [third]


def test_nothing_is_added_when_the_recalled_memories_have_no_links_either_way():
    assert asyncio.run(with_linked(fetcher(OLD, FIX), [LEAVE])) == [LEAVE]


def test_a_memory_is_never_added_twice():
    out = asyncio.run(with_linked(fetcher(OLD, FIX), [OLD, FIX]))
    assert [r["id"] for r in out] == ["a", "b"]


def test_no_recalled_rows_means_no_database_call():
    fetch = fetcher(OLD)
    assert asyncio.run(with_linked(fetch, [])) == [] and fetch.calls == []


def test_the_lookup_stops_after_a_few_rounds_even_if_the_database_keeps_returning_new_rows():
    counter = iter(range(100))

    async def endless(ids, recalled):
        return [row(f"x{next(counter)}", "chain", 1)]
    assert len(asyncio.run(with_linked(endless, [OLD]))) == 1 + 3


# c) valid_links

EXISTING = [row("a", "old a", 1), row("b", "old b", 2)]
NEW_AT = datetime(2026, 11, 5)


def test_links_to_existing_older_memories_are_kept():
    assert valid_links(EXISTING, ["a", "b"], NEW_AT) == (["a", "b"], [])


def test_a_link_to_an_unknown_memory_is_dropped_and_returned_separately():
    assert valid_links(EXISTING, ["a", "zzz"], NEW_AT) == (["a"], ["zzz"])


def test_a_link_to_a_memory_that_is_not_older_is_dropped():
    assert valid_links(EXISTING, ["a", "b"], datetime(2026, 11, 2)) == (["a"], ["b"])   # b was created the same day, not before


def test_a_repeated_link_is_kept_once():
    assert valid_links(EXISTING, ["a", "a"], NEW_AT) == (["a"], [])


# attach_earlier and render_memories

def test_a_current_memory_gets_the_text_of_the_ones_it_replaced():
    everything = [OLD, FIX, LEAVE]
    out = attach_earlier(current_memories(everything), everything)
    assert out[0]["earlier"] == ["User filed a medical claim for 15,000"]
    assert out[1]["earlier"] == []


def test_render_shows_earlier_text_after_the_memory_that_replaced_it():
    text = render_memories([{**FIX, "earlier": [OLD["text"]]}, {**LEAVE, "earlier": []}])
    assert "1. User corrected the medical claim amount from 15,000 to 12,500 (earlier: User filed a medical claim for 15,000)" in text
    assert "2. User applied for leave from 12 Dec to 19 Dec\n" in text + "\n"


def test_render_without_earlier_is_unchanged():
    assert "1. User applied for leave from 12 Dec to 19 Dec" in render_memories([LEAVE])
    assert "earlier" not in render_memories([LEAVE]).split("\n", 1)[1]
    assert render_memories([]) == ""
