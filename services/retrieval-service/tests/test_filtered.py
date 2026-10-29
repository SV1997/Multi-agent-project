"""Phase 3: filtered retrieval (LOCALIZE). Run from services/retrieval-service:  python -m pytest tests/test_filtered.py

The vector store and the keyword index are fakes, so no network and no database are used; the real
query_namespace and the real filter functions run.
"""
import asyncio
import importlib
import os
import sys
import types

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))
fake_emb = types.ModuleType("shared.embeddings.embeddings")
fake_emb.embeddings = object()
sys.modules.setdefault("shared.embeddings.embeddings", fake_emb)

from langchain_core.documents import Document  # noqa: E402
from app.core import config  # noqa: E402
from app.pinecone import namespace_router as ns  # noqa: E402
from app.pinecone.filters import pinecone_filter, keyword_chunk_allowed, chunk_tags  # noqa: E402
from shared.contracts.schema import RetrievalQuery  # noqa: E402

CONTENT_ONLY = {"is_content": {"$eq": True}}


class FakeStore:
    """Records how it was searched, and returns whatever documents the test put in `results`."""
    calls: list = []
    results: list = []
    unfiltered = None          # what a search WITHOUT a filter returns; None means the same as `results`
    sequence = None            # when set, the n-th search returns sequence[n] (the last one repeats)

    def __init__(self, **_):
        pass

    def similarity_search_with_score(self, *args, **kwargs):
        FakeStore.calls.append(kwargs)
        documents = FakeStore.results
        if FakeStore.sequence is not None:
            documents = FakeStore.sequence[min(len(FakeStore.calls) - 1, len(FakeStore.sequence) - 1)]
        elif "filter" not in kwargs and FakeStore.unfiltered is not None:
            documents = FakeStore.unfiltered
        return [(doc, 0.0) for doc in documents[: kwargs["k"]]]


class FakeBm25:
    def __init__(self, scores):
        self.scores = scores

    def get_scores(self, _tokens):
        return self.scores


def chunk(text, score_order=None, **labels):
    return {"text": text, "source": "s.pdf", **labels}


# five keyword chunks, in the order the fake index scores them (highest score first):
#   B 9 (right kind, wrong category) | C 8 (no labels) | D 7 (not content) | E 6 (plain string) | A 5 | F 4
BM25_CHUNKS = [
    chunk("B", categories=["pay"], is_content=True),
    chunk("C"),
    chunk("D", categories=["leave"], is_content=False),
    "E old plain string chunk",
    chunk("A", categories=["leave"], is_content=True, title="Handbook"),
    chunk("F", categories=["leave", "pay"], is_content=True),
]
BM25_SCORES = [9.0, 8.0, 7.0, 6.0, 5.0, 4.0]


@pytest.fixture
def search(monkeypatch):
    """search(localize=..., categories=..., vector=[...]) -> (results by text, kwargs of the vector search)."""
    monkeypatch.setattr(ns, "PineconeVectorStore", FakeStore)
    monkeypatch.setattr(config, "RERANK_ENABLED", False)

    has_index = {"on": True}

    async def fake_bm25(_namespace):
        # a namespace with no stored keyword index gives None, as the real load_bm25 does
        return {"Bm25": FakeBm25(BM25_SCORES), "chunks": BM25_CHUNKS} if has_index["on"] else None

    monkeypatch.setattr(ns, "load_bm25", fake_bm25)

    def run(localize="off", categories=None, vector=(), top_k=10, namespace="hr", keyword_index=True, unfiltered=None, wider=None, sequence=None):
        monkeypatch.setattr(config, "LOCALIZE", localize)
        has_index["on"] = keyword_index
        FakeStore.calls = []
        FakeStore.results = list(vector)
        FakeStore.unfiltered = list(unfiltered) if unfiltered is not None else None
        FakeStore.sequence = [list(step) for step in sequence] if sequence is not None else None
        # model_construct skips validation: the contract only allows the five domains, and "coding" is meant to
        # show what happens if a request for it ever got this far
        request = RetrievalQuery.model_construct(query="how many leave days", namespace=namespace, top_k=top_k,
                                                 categories=categories, wider_categories=wider)
        response = asyncio.run(ns.query_namespace(request))
        run.response = response
        return {c.content: c for c in response.results}, FakeStore.calls[0]

    return run


# ---------------------------------------------------------------- the switch is off: nothing changes

def test_with_localize_off_the_search_is_exactly_what_it_was(search):
    results, vector_call = search(localize="off", categories=["leave"])

    assert set(vector_call) == {"query", "k"}                       # no filter argument at all
    assert set(results) == {"B", "C", "D", "A", "F", "E old plain string chunk"}     # nothing dropped
    assert results["A"].metadata == {"source": "s.pdf"}                              # keyword hits show only the source, as before


# ---------------------------------------------------------------- the Pinecone filter

def test_the_vector_search_gets_a_content_and_category_filter(search):
    _, vector_call = search(localize="on", categories=["leave", "earned_leave"])
    assert vector_call["filter"] == {"$and": [{"categories": {"$in": ["leave", "earned_leave"]}}, CONTENT_ONLY]}


@pytest.mark.parametrize("categories", [None, []])
def test_without_categories_only_the_content_rule_applies(search, categories):
    _, vector_call = search(localize="on", categories=categories)
    assert vector_call["filter"] == CONTENT_ONLY


def test_with_localize_on_a_request_with_categories_is_filtered(search):
    _, vector_call = search(localize="on", categories=["leave"])
    assert "filter" in vector_call


# ---------------------------------------------------------------- the keyword filter

def test_keyword_search_keeps_only_content_chunks_in_the_requested_categories(search):
    results, _ = search(localize="on", categories=["leave"])
    assert set(results) == {"A", "F"}        # B wrong category, C no labels, D not content, E plain string


def test_keyword_ranks_are_counted_after_filtering(search):
    results, _ = search(localize="on", categories=["leave"])
    # A and F are the 5th and 6th best keyword hits, but after filtering they are ranks 1 and 2
    assert results["A"].score == pytest.approx(1 / 61)
    assert results["F"].score == pytest.approx(1 / 62)


def test_without_categories_keyword_search_keeps_every_content_chunk(search):
    results, _ = search(localize="on", categories=None)
    assert set(results) == {"B", "A", "F"}


def test_keyword_only_hits_carry_their_labels(search):
    results, _ = search(localize="on", categories=["leave"])
    assert results["A"].metadata == {"source": "s.pdf", "categories": ["leave"], "is_content": True, "title": "Handbook"}


def test_a_text_found_by_both_searches_adds_both_ranks(search):
    both = Document(page_content="A", metadata={"source": "s.pdf", "categories": ["leave"], "is_content": True})
    results, _ = search(localize="on", categories=["leave"], vector=[both])
    assert results["A"].score == pytest.approx(1 / 61 + 1 / 61)          # vector rank 1 and keyword rank 1
    assert results["A"].metadata["categories"] == ["leave"]               # the vector search's own metadata is kept


# ---------------------------------------------------------------- one fallback when the filtered search finds nothing

def labelled(text):
    return Document(page_content=text, metadata={"source": "s.pdf", "categories": ["pay"], "is_content": True})


def test_without_a_wider_level_a_search_with_zero_results_goes_straight_to_one_unfiltered_search(search):
    results, _ = search(localize="on", categories=["tax"], vector=[], unfiltered=[labelled("W")])
    assert len(FakeStore.calls) == 2
    assert "filter" in FakeStore.calls[0] and "filter" not in FakeStore.calls[1]      # the second search has no filter at all
    assert search.response.fallback_used is True and "W" in results


def test_a_search_that_finds_something_does_not_fall_back(search):
    search(localize="on", categories=["leave"], vector=[labelled("V")], unfiltered=[labelled("W")])
    assert len(FakeStore.calls) == 1 and search.response.fallback_used is False


def test_the_fallback_runs_once_even_if_the_unfiltered_search_is_empty_too(search):
    results, _ = search(localize="on", categories=["tax"], vector=[], unfiltered=[], keyword_index=False)
    assert len(FakeStore.calls) == 2 and results == {} and search.response.fallback_used is True


def test_with_localize_off_an_empty_search_does_not_retry(search):
    search(localize="off", categories=["tax"], vector=[], keyword_index=False)
    assert len(FakeStore.calls) == 1 and search.response.fallback_used is False


def test_without_categories_there_is_nothing_to_fall_back_from(search):
    search(localize="on", categories=None, vector=[], keyword_index=False)
    assert len(FakeStore.calls) == 1 and search.response.fallback_used is False


# ---------------------------------------------------------------- widening: own categories, parents' family, whole domain

WIDER = ["leave", "earned_leave", "sick_leave"]


def test_level_one_is_tried_when_the_frames_own_categories_find_nothing(search):
    results, _ = search(localize="on", categories=["earned_leave"], wider=WIDER, sequence=[[], [labelled("W")]], keyword_index=False)
    assert len(FakeStore.calls) == 2
    assert FakeStore.calls[1]["filter"] == pinecone_filter(WIDER)                   # the second search is filtered to the family
    assert "W" in results and search.response.fallback_level == 1 and search.response.fallback_used is True


def test_level_two_is_the_whole_domain_with_no_filter(search):
    search(localize="on", categories=["earned_leave"], wider=WIDER, sequence=[[], [], [labelled("W")]], keyword_index=False)
    assert len(FakeStore.calls) == 3
    assert "filter" in FakeStore.calls[0] and "filter" in FakeStore.calls[1] and "filter" not in FakeStore.calls[2]
    assert search.response.fallback_level == 2


def test_a_level_that_finds_something_stops_the_widening(search):
    search(localize="on", categories=["earned_leave"], wider=WIDER, sequence=[[], [labelled("W")], [labelled("X")]], keyword_index=False)
    assert len(FakeStore.calls) == 2 and search.response.fallback_level == 1


def test_a_search_that_finds_something_at_level_zero_does_not_widen(search):
    search(localize="on", categories=["earned_leave"], wider=WIDER, sequence=[[labelled("V")], [labelled("W")]], keyword_index=False)
    assert len(FakeStore.calls) == 1 and search.response.fallback_level == 0 and search.response.fallback_used is False


def test_every_level_is_tried_once_and_no_more_even_if_all_are_empty(search):
    results, _ = search(localize="on", categories=["earned_leave"], wider=WIDER, sequence=[[]], keyword_index=False)
    assert len(FakeStore.calls) == 3 and results == {} and search.response.fallback_level == 2


def test_without_a_wider_level_level_one_is_skipped_but_the_whole_domain_is_still_level_two(search):
    search(localize="on", categories=["leave"], wider=None, sequence=[[], [labelled("W")]], keyword_index=False)
    assert len(FakeStore.calls) == 2 and "filter" not in FakeStore.calls[1] and search.response.fallback_level == 2


def test_the_keyword_search_is_widened_to_the_family_too(search):
    # nothing is labelled "tax", but the keyword chunks A and F are labelled "leave", which the wider level covers
    results, _ = search(localize="on", categories=["tax"], wider=["leave"], sequence=[[]])
    assert len(FakeStore.calls) == 2 and set(results) == {"A", "F"} and search.response.fallback_level == 1


def test_with_localize_off_the_wider_categories_are_ignored(search):
    search(localize="off", categories=["earned_leave"], wider=WIDER, sequence=[[]], keyword_index=False)
    assert len(FakeStore.calls) == 1 and search.response.fallback_level == 0


def test_the_request_contract_has_optional_wider_categories():
    assert RetrievalQuery(query="q", namespace="hr").wider_categories is None
    assert RetrievalQuery(query="q", namespace="hr", wider_categories=["leave"]).wider_categories == ["leave"]


# ---------------------------------------------------------------- a domain without a keyword index (support)

@pytest.mark.parametrize("level", ["off", "on"])
def test_a_missing_keyword_index_falls_back_to_vector_only(search, level):
    found = Document(page_content="V", metadata={"source": "s.pdf", "categories": ["leave"], "is_content": True})
    results, vector_call = search(level, categories=["leave"], vector=[found], namespace="support", keyword_index=False)

    assert set(results) == {"V"}                                     # vector hit only, and no crash
    assert results["V"].score == pytest.approx(1 / 61)               # one rank, no keyword rank added
    assert ("filter" in vector_call) == (level != "off")             # the vector search is still localized


def test_the_real_loader_returns_none_when_the_namespace_has_no_row(monkeypatch):
    from app.storage import bm25score

    class NoRowConn:
        async def fetchrow(self, query, namespace):
            return None

        async def close(self):
            pass

    async def connect():
        return NoRowConn()

    monkeypatch.setattr(bm25score, "get_connection", connect)
    assert asyncio.run(bm25score.load_bm25("support")) is None


# ---------------------------------------------------------------- a namespace outside the taxonomy (coding)

def test_the_request_contract_does_not_accept_the_coding_namespace():
    with pytest.raises(ValueError):
        RetrievalQuery(query="q", namespace="coding")


def test_a_namespace_outside_the_taxonomy_is_searched_exactly_as_with_localize_off(search):
    found = Document(page_content="code", metadata={"source": "x.py"})        # coding chunks carry no labels
    off_results, off_call = search("off", categories=["leave"], vector=[found], namespace="coding")
    full_results, full_call = search("on", categories=["leave"], vector=[found], namespace="coding")

    assert set(full_call) == {"query", "k"} == set(off_call)                  # no filter argument at all
    assert set(full_results) == set(off_results)                              # the unlabeled keyword chunks are kept too
    assert {c.score for c in full_results.values()} == {c.score for c in off_results.values()}
    assert "code" in full_results and "C" in full_results                     # unlabeled chunks are not hidden
    assert full_results["C"].metadata == {"source": "s.pdf"}                  # and show no labels, as with off


def test_the_localized_namespaces_match_the_taxonomy_domains():
    from shared.taxonomy.taxonomy import DOMAINS
    from app.pinecone.filters import LOCALIZED_NAMESPACES
    assert set(LOCALIZED_NAMESPACES) == set(DOMAINS)


# ---------------------------------------------------------------- the pure functions

@pytest.mark.parametrize("chunk_value, categories, expected", [
    ({"categories": ["leave"], "is_content": True}, ["leave"], True),
    ({"categories": ["leave", "pay"], "is_content": True}, ["pay", "tax"], True),       # any overlap is enough
    ({"categories": ["leave"], "is_content": True}, ["pay"], False),
    ({"categories": ["leave"], "is_content": False}, ["leave"], False),                 # not content
    ({"categories": ["leave"]}, ["leave"], False),                                      # no is_content label
    ({"categories": ["leave"], "is_content": "true"}, ["leave"], False),                # must be a real True
    ({"is_content": True}, ["leave"], False),                                           # no categories label
    ({"categories": [], "is_content": True}, ["leave"], False),
    ({"is_content": True}, None, True),                                                 # no categories asked: content is enough
    ({"is_content": True}, [], True),
    ("plain old string", None, False),
    ("plain old string", ["leave"], False),
])
def test_keyword_chunk_allowed(chunk_value, categories, expected):
    assert keyword_chunk_allowed(chunk_value, categories) is expected


def test_pinecone_filter_does_not_alias_the_callers_list():
    wanted = ["leave"]
    built = pinecone_filter(wanted)
    wanted.append("pay")
    assert built["$and"][0]["categories"]["$in"] == ["leave"]


def test_chunk_tags_returns_only_the_label_fields():
    assert chunk_tags({"text": "t", "source": "s", "categories": ["a"], "is_content": True, "doc_id": "d"}) == \
        {"categories": ["a"], "is_content": True}
    assert chunk_tags("plain") == {}


# ---------------------------------------------------------------- the contract and the setting

def test_the_request_contract_has_optional_categories():
    assert RetrievalQuery(query="q", namespace="hr").categories is None
    assert RetrievalQuery(query="q", namespace="hr", categories=["leave"]).categories == ["leave"]


@pytest.mark.parametrize("value, expected", [(None, "off"), ("on", "on"), (" ON ", "on"), ("off", "off"), ("filter", "off"), ("full", "off"), ("nonsense", "off")])
def test_the_setting_reads_the_environment_and_falls_back_to_off(monkeypatch, value, expected):
    try:
        if value is None:
            monkeypatch.delenv("LOCALIZE", raising=False)
        else:
            monkeypatch.setenv("LOCALIZE", value)
        assert importlib.reload(config).LOCALIZE == expected
    finally:
        monkeypatch.undo()
        importlib.reload(config)          # leave the module as the other tests expect it
