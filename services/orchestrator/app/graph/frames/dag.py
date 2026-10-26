"""A small graph that records how ONE question was handled, so the localization can be inspected afterwards.

Why this file exists: the examiner asked for "a Frame or a DAG structure for queries". The frame is the decision;
this is the trace of it. For every question it records: the question -> the frame it was sorted into -> the
categories that frame searches -> the parents of those categories (the taxonomy's own DAG) -> and each piece of
evidence that was retrieved, attached under the category it carries and marked as inside or outside the frame.

Problem it solves: "why did it answer from there?" becomes answerable by looking at one structure. It also
shows, for a single question, whether retrieval stayed inside the frame or pulled in evidence from elsewhere
(for example after widening to a parent category, or with localization off).

Shape (plain JSON, so it can be logged, stored in the checkpoint and returned with the answer):
    {"nodes": [{"id", "type", "label", ...}], "edges": [{"from", "to", "label"}],
     "frame_id", "categories", "evidence_total", "evidence_outside_frame"}
Edges run query -> frame -> category -> parent category, and category -> evidence, so the graph has no cycle.
Evidence that carries no category information (for example a database record) hangs directly under the query,
with in_frame = None ("unknown"), and is not counted as outside.
"""
import logging

from .node import latest_message

logger = logging.getLogger(__name__)


def build_query_dag(taxonomy, state) -> dict:
    nodes: dict[str, dict] = {}
    edges: list[dict] = []

    def add_node(node_id: str, **data):
        nodes.setdefault(node_id, {"id": node_id, **data})

    def add_edge(source: str, target: str, label: str):
        edges.append({"from": source, "to": target, "label": label})

    domain = state.get("domain")
    frame_id = state.get("frame_id")
    frame_categories = list(state.get("localize_categories") or [])
    domain_categories = taxonomy.categories.get(domain, {}) if taxonomy is not None else {}

    add_node("query", type="query", label=latest_message(state)[:200])

    if frame_id:
        add_node("frame", type="frame", label=frame_id,
                 slots=dict(state.get("frame_slots") or {}), missing_slots=list(state.get("missing_slots") or []))
        add_edge("query", "frame", "sorted into")
        queue = list(frame_categories)
        for name in frame_categories:
            add_node(f"category:{name}", type="category", label=name, role="frame")
            add_edge("frame", f"category:{name}", "searches")
        seen = set(frame_categories)
        while queue:                                    # walk up the taxonomy so the parents are on the graph too
            name = queue.pop(0)
            for parent in (domain_categories[name].parents if name in domain_categories else ()):
                add_node(f"category:{parent}", type="category", label=parent, role="parent")
                add_edge(f"category:{name}", f"category:{parent}", "is part of")
                if parent not in seen:
                    seen.add(parent)
                    queue.append(parent)

    outside = 0
    chunks = state.get("retrieved_context") or []
    for number, chunk in enumerate(chunks, 1):
        metadata = chunk.get("metadata") or {}
        categories = list(metadata.get("categories") or [])
        if not categories:
            in_frame = None
        elif not frame_categories:
            in_frame = True if frame_id else None       # "other" searches the whole domain; no frame = nothing to compare to
        else:
            in_frame = bool(set(categories) & set(frame_categories))
        if in_frame is False:
            outside += 1
        evidence_id = f"evidence:{number}"
        add_node(evidence_id, type="evidence", label=str(chunk.get("source", "unknown"))[-80:],
                 categories=categories, in_frame=in_frame, score=chunk.get("score"))
        if not categories:
            add_edge("query", evidence_id, "retrieved")
        for name in categories:
            add_node(f"category:{name}", type="category", label=name, role="outside")   # no-op if already on the graph
            add_edge(f"category:{name}", evidence_id, "found under")

    return {
        "nodes": list(nodes.values()),
        "edges": edges,
        "frame_id": frame_id,
        "categories": frame_categories,
        "evidence_total": len(chunks),
        "evidence_outside_frame": outside,
    }


def make_trace_node(taxonomy, level=lambda: "off"):
    """Graph node that stores the DAG in the state once the answer is known. Never allowed to break an answer."""
    def trace_query(state) -> dict:
        if level() == "off" or taxonomy is None:
            return {}
        try:
            return {"query_dag": build_query_dag(taxonomy, state)}
        except Exception:
            logger.exception("Could not build the query DAG")
            return {}
    return trace_query


def debug_payload(values: dict) -> dict | None:
    """What is returned next to the answer for inspection: the frame decision and the DAG. None when no frame was used."""
    if not values or not values.get("frame_id"):
        return None
    return {
        "frame_id": values.get("frame_id"),
        "frame_slots": values.get("frame_slots"),
        "missing_slots": values.get("missing_slots"),
        "categories": values.get("localize_categories"),
        "rewritten_query": values.get("rewritten_query"),
        "clarifying_question": values.get("clarifying_question"),
        "query_dag": values.get("query_dag"),
    }
