"""Phase 4: the per-query DAG (query -> frame -> categories -> parents -> evidence).
Run from services/orchestrator:  python -m pytest tests/test_query_dag.py
"""
import json
import os
import sys

from langchain_core.messages import HumanMessage

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))
from shared.taxonomy.taxonomy import parse_taxonomy  # noqa: E402
from app.graph.frames.dag import build_query_dag, make_trace_node, debug_payload  # noqa: E402

TAX = parse_taxonomy({
    "hr": {
        "categories": {
            "leave": {"description": "All leave rules", "parents": []},
            "earned_leave": {"description": "Earned leave", "parents": ["leave"]},
            "sick_leave": {"description": "Sick leave", "parents": ["leave"]},
            "payroll": {"description": "Salary payment", "parents": []},
            "tax_docs": {"description": "Tax documents", "parents": ["payroll"]},
        },
        "documents": {"handbook.pdf": ["leave", "earned_leave", "sick_leave", "payroll", "tax_docs"]},
    }
})


def chunk(source, categories, score=0.5):
    return {"source": source, "content": "text", "score": score, "metadata": {"categories": categories}}


def state_of(**extra):
    base = {"domain": "hr", "messages": [HumanMessage(content="how many earned leave days do I get?")]}
    return {**base, **extra}


def node(dag, node_id):
    return next(n for n in dag["nodes"] if n["id"] == node_id)


def edge_pairs(dag):
    return {(e["from"], e["to"]) for e in dag["edges"]}


def is_acyclic(dag) -> bool:
    nodes = {n["id"] for n in dag["nodes"]}
    incoming = {n: 0 for n in nodes}
    for e in dag["edges"]:
        incoming[e["to"]] += 1
    ready = [n for n, c in incoming.items() if c == 0]
    visited = 0
    while ready:
        current = ready.pop()
        visited += 1
        for e in dag["edges"]:
            if e["from"] == current:
                incoming[e["to"]] -= 1
                if incoming[e["to"]] == 0:
                    ready.append(e["to"])
    return visited == len(nodes)


FRAMED = dict(frame_id="hr.earned_leave", localize_categories=["earned_leave"], frame_slots={"leave_type": "earned"}, missing_slots=[])


def test_the_chain_runs_from_the_query_through_the_frame_and_categories_to_the_evidence():
    dag = build_query_dag(TAX, state_of(**FRAMED, retrieved_context=[chunk("handbook.pdf", ["earned_leave"])]))

    assert edge_pairs(dag) == {
        ("query", "frame"),
        ("frame", "category:earned_leave"),
        ("category:earned_leave", "category:leave"),          # the taxonomy's parent
        ("category:earned_leave", "evidence:1"),
    }
    assert node(dag, "query")["label"] == "how many earned leave days do I get?"
    assert node(dag, "frame")["label"] == "hr.earned_leave" and node(dag, "frame")["slots"] == {"leave_type": "earned"}
    assert node(dag, "category:earned_leave")["role"] == "frame" and node(dag, "category:leave")["role"] == "parent"
    assert is_acyclic(dag)


def test_evidence_outside_the_frame_is_marked_and_counted():
    dag = build_query_dag(TAX, state_of(**FRAMED, retrieved_context=[
        chunk("a.pdf", ["earned_leave"]), chunk("b.pdf", ["sick_leave"]), chunk("c.pdf", ["sick_leave", "earned_leave"])]))

    assert [node(dag, f"evidence:{i}")["in_frame"] for i in (1, 2, 3)] == [True, False, True]   # any overlap is inside
    assert node(dag, "category:sick_leave")["role"] == "outside"
    assert dag["evidence_total"] == 3 and dag["evidence_outside_frame"] == 1
    assert is_acyclic(dag)


def test_all_ancestors_of_a_frame_category_are_on_the_graph():
    tax = parse_taxonomy({"hr": {
        "categories": {"a": {"description": "d", "parents": []}, "b": {"description": "d", "parents": ["a"]},
                       "c": {"description": "d", "parents": ["b"]}},
        "documents": {"f.pdf": ["a", "b", "c"]}}})
    dag = build_query_dag(tax, state_of(frame_id="hr.c", localize_categories=["c"]))
    assert {("category:c", "category:b"), ("category:b", "category:a")} <= edge_pairs(dag)


def test_evidence_with_no_category_information_is_unknown_not_outside():
    dag = build_query_dag(TAX, state_of(**FRAMED, retrieved_context=[{"source": "sql:leave_balance", "content": "12", "score": 1.0}]))
    assert node(dag, "evidence:1")["in_frame"] is None and ("query", "evidence:1") in edge_pairs(dag)
    assert dag["evidence_outside_frame"] == 0


def test_the_other_frame_searches_everything_so_labelled_evidence_is_inside():
    dag = build_query_dag(TAX, state_of(frame_id="hr.other", localize_categories=None, retrieved_context=[chunk("a.pdf", ["payroll"])]))
    assert node(dag, "evidence:1")["in_frame"] is True and dag["categories"] == []


def test_without_a_frame_there_is_only_the_query_and_the_evidence():
    dag = build_query_dag(TAX, state_of(retrieved_context=[chunk("a.pdf", ["payroll"])]))
    assert {n["type"] for n in dag["nodes"]} == {"query", "evidence", "category"}
    assert dag["frame_id"] is None and node(dag, "evidence:1")["in_frame"] is None
    assert is_acyclic(dag)


def test_the_dag_is_plain_json():
    dag = build_query_dag(TAX, state_of(**FRAMED, retrieved_context=[chunk("a.pdf", ["earned_leave"], score=0.123)]))
    assert json.loads(json.dumps(dag)) == dag


# ---------------------------------------------------------------- the trace step and the debug payload

def test_the_trace_step_does_nothing_when_localization_is_off():
    assert make_trace_node(TAX, level=lambda: "off")(state_of(**FRAMED)) == {}
    assert make_trace_node(None, level=lambda: "filter")(state_of(**FRAMED)) == {}


def test_the_trace_step_stores_the_dag_when_localization_is_on():
    update = make_trace_node(TAX, level=lambda: "filter")(state_of(**FRAMED, retrieved_context=[]))
    assert update["query_dag"]["frame_id"] == "hr.earned_leave"


def test_a_failure_while_tracing_never_breaks_the_answer():
    class BrokenTaxonomy:
        @property
        def categories(self):
            raise RuntimeError("boom")
    assert make_trace_node(BrokenTaxonomy(), level=lambda: "full")(state_of(**FRAMED)) == {}


def test_debug_information_is_returned_only_when_a_frame_was_used():
    assert debug_payload({}) is None and debug_payload({"frame_id": None, "query_dag": {"x": 1}}) is None
    payload = debug_payload({**FRAMED, "rewritten_query": "q", "clarifying_question": None, "query_dag": {"nodes": []}})
    assert payload == {"frame_id": "hr.earned_leave", "frame_slots": {"leave_type": "earned"}, "missing_slots": [],
                       "categories": ["earned_leave"], "fallback_level": None, "levels_tried": None,
                       "rewritten_query": "q", "clarifying_question": None, "query_dag": {"nodes": []}}


# ---------------------------------------------------------------- widening shows up in the trace

def test_the_dag_records_which_level_the_evidence_came_from():
    state = state_of(**FRAMED, fallback_level=1, levels_tried=[0, 1],
                     retrieved_context=[chunk("a.pdf", ["sick_leave"])])
    dag = build_query_dag(TAX, state)
    assert dag["fallback_level"] == 1 and dag["levels_tried"] == [0, 1]
    assert node(dag, "evidence:1")["in_frame"] is False and dag["evidence_outside_frame"] == 1   # a wider level = outside the frame


def test_the_dag_has_no_level_when_nothing_was_searched():
    dag = build_query_dag(TAX, state_of(**FRAMED, retrieved_context=[]))
    assert dag["fallback_level"] is None and dag["levels_tried"] == []


def test_debug_information_carries_the_levels():
    payload = debug_payload({**FRAMED, "fallback_level": 2, "levels_tried": [0, 1, 2]})
    assert payload["fallback_level"] == 2 and payload["levels_tried"] == [0, 1, 2]


def test_the_trace_step_logs_the_level_that_answered(caplog):
    import logging
    state = state_of(**FRAMED, fallback_level=1, levels_tried=[0, 1], retrieved_context=[chunk("a.pdf", ["sick_leave"])])
    with caplog.at_level(logging.INFO, logger="app.graph.frames.dag"):
        make_trace_node(TAX, level=lambda: "filter")(state)
    assert any("level 1" in r.message and "levels searched [0, 1]" in r.message and "1 outside the frame" in r.message
               for r in caplog.records)
