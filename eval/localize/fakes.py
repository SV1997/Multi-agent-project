"""A fake orchestrator for `run-all --dry-run`: it lets the whole pipeline run with no services and no keys.

Why this file exists: to check the output format (result files, comparison table) before spending a live run.
Everything it returns is made up from a hash of the question id and the level, so it is repeatable. NOTHING
produced with it says anything about the real system, and the dry run labels every file it writes as fake.

What it imitates: LOCALIZE=off returns no frame; the other levels return the expected frame most of the time, a
mix of widening levels, a clarifying question at "full" when one is needed, sources that are sometimes outside
the expected categories, and some requests that time out (so the failure path is exercised too).
"""
import hashlib


def _pick(question_id: str, level: str, salt: str, modulo: int) -> int:
    return int(hashlib.sha1(f"{question_id}|{level}|{salt}".encode()).hexdigest()[:8], 16) % modulo


class FakeClient:
    def __init__(self, level: str, taxonomy):
        self.level = level
        self.taxonomy = taxonomy

    def _source(self, row: dict, wanted_overlap: bool) -> str | None:
        expected = set(row["expected_categories"])
        files = sorted(name for name, cats in self.taxonomy.documents.get(row["domain"], {}).items()
                       if bool(set(cats) & expected) == wanted_overlap)
        return files[_pick(row["id"], self.level, "source", len(files))] if files else None

    def __call__(self, row: dict) -> dict:
        if _pick(row["id"], self.level, "fail", 6) == 0:
            raise TimeoutError("FAKE timeout (dry run)")
        in_category = _pick(row["id"], self.level, "cat", 4) != 0                    # about a quarter cite outside it
        source = self._source(row, in_category) or self._source(row, not in_category)
        body = {"answer": f"FAKE ANSWER (dry run) to {row['id']}", "sources": [source] if source else [],
                "confidence": 0.5, "debug": None}
        if self.level == "off":
            return body

        right_frame = _pick(row["id"], self.level, "frame", 5) != 0                   # about a fifth are sorted wrongly
        frame = row["expected_frame"] if right_frame else f"{row['domain']}.other"
        asked = self.level == "full" and (row["needs_clarification"] != (_pick(row["id"], self.level, "ask", 5) == 0))
        body["debug"] = {
            "frame_id": frame, "frame_slots": {}, "missing_slots": [], "categories": row["expected_categories"] or None,
            "fallback_level": _pick(row["id"], self.level, "level", 3), "levels_tried": [0],
            "rewritten_query": None, "clarifying_question": "FAKE clarifying question?" if asked else None,
            "query_dag": None,
        }
        return body
