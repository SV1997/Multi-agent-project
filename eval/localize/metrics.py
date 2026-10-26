"""The five numbers the evaluation reports, worked out from what the system returned for each question.

Why this file exists: "localized search is better" needs numbers, and the numbers need one fixed definition each
so the four LOCALIZE levels are compared in the same way. These are plain functions over plain dicts, so they are
tested with made-up results and no running service.

Problem it solves: a metric that quietly counts "not available" as zero would make LOCALIZE=off look worse (or
better) than it is. Every metric returns None - shown as n/a - when there is nothing to measure it on, and always
says how many questions it was measured on.

The metrics (a "result" is what the runner stored for one question: answer, sources, debug, error):
    wrong_category_citation   of the sources the answer cited whose categories are known, the share whose
                              categories share nothing with the question's expected_categories. Sources in a
                              document with mixed categories, or not in the taxonomy, cannot be judged and are
                              counted separately ("unjudged"), not as right or wrong. Needs expected_categories.
    frame_accuracy            of the questions with an expected_frame, the share sorted into exactly that frame.
                              A question for which no frame was chosen counts as wrong. n/a at LOCALIZE=off,
                              where no frame is chosen on purpose.
    clarification_correct     of all questions, the share where "asked the user a clarifying question" matches
                              needs_clarification. Only the "full" level asks, so it is n/a below it.
    fallback_rate             of the questions that got a frame, the share whose evidence came from a widened
                              search (level 1 or 2) rather than the frame's own categories.
    gap                       tune value minus heldout value for each metric above: a large gap means the frames
                              and prompts were fitted to the tuning questions.
A result with an error (the request failed) is left out of every metric and counted under "errors".
"""
from collections import defaultdict

METRICS = ("wrong_category_citation", "frame_accuracy", "clarification_correct", "fallback_rate")


def ratio(part: int, whole: int) -> dict:
    return {"value": (part / whole) if whole else None, "n": whole, "count": part}


def source_categories(taxonomy, domain: str, source: str):
    """Categories of a cited source's document, or None when they cannot be told (mixed document / not in the taxonomy)."""
    key = taxonomy.document_key(domain, source)
    if key is None or taxonomy.is_mixed(domain, source):
        return None
    return set(taxonomy.documents[domain][key])


def wrong_category_citation(pairs, taxonomy) -> dict:
    wrong = judged = unjudged = 0
    for row, result in pairs:
        expected = set(row["expected_categories"])
        if not expected:
            continue
        for source in dict.fromkeys(result.get("sources") or []):          # each distinct source once per question
            categories = source_categories(taxonomy, row["domain"], source)
            if categories is None:
                unjudged += 1
                continue
            judged += 1
            wrong += not (categories & expected)
    out = ratio(wrong, judged)
    out["unjudged"] = unjudged
    return out


def frame_accuracy(pairs, level: str) -> dict:
    if level == "off":
        return ratio(0, 0)
    asked = [(row, result) for row, result in pairs if row["expected_frame"] is not None]
    right = sum(1 for row, result in asked if (result.get("debug") or {}).get("frame_id") == row["expected_frame"])
    return ratio(right, len(asked))


def clarification_correct(pairs, level: str) -> dict:
    if level != "full":
        return ratio(0, 0)
    right = sum(1 for row, result in pairs
                if bool((result.get("debug") or {}).get("clarifying_question")) == row["needs_clarification"])
    return ratio(right, len(pairs))


def fallback_rate(pairs) -> dict:
    framed = [result["debug"] for _, result in pairs if (result.get("debug") or {}).get("frame_id")]
    widened = sum(1 for debug in framed if debug.get("fallback_level") not in (None, 0))
    return ratio(widened, len(framed))


def compute(rows: list[dict], results: dict, taxonomy, level: str) -> dict:
    """All metrics for one level, over everything and then per split, plus the tune - heldout gap."""
    pairs, errors = [], 0
    for row in rows:
        result = results.get(row["id"])
        if result is None or result.get("error"):
            errors += 1
        else:
            pairs.append((row, result))

    def metrics_for(subset) -> dict:
        return {
            "questions": len(subset),
            "wrong_category_citation": wrong_category_citation(subset, taxonomy),
            "frame_accuracy": frame_accuracy(subset, level),
            "clarification_correct": clarification_correct(subset, level),
            "fallback_rate": fallback_rate(subset),
        }

    by_split = defaultdict(list)
    for pair in pairs:
        by_split[pair[0]["split"]].append(pair)
    report = {"level": level, "errors": errors, "all": metrics_for(pairs),
              "tune": metrics_for(by_split["tune"]), "heldout": metrics_for(by_split["heldout"]), "gap": {}}
    for name in METRICS:
        tune, heldout = report["tune"][name]["value"], report["heldout"][name]["value"]
        report["gap"][name] = None if tune is None or heldout is None else tune - heldout
    return report


def percent(value) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"
