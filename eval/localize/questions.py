"""Reading and checking the evaluation question set (JSON Lines, one question per line).

Why this file exists: the examiner will ask "how do you know localized search is better?". That needs a fixed
set of questions with known right answers, split into questions used while tuning the frames and prompts
("tune") and questions never looked at while tuning ("heldout"). This file defines the format and refuses a file
that is malformed, so a typo in the set cannot silently change a result.

Problem it solves: a question set written by hand drifts (a category renamed in the taxonomy, a duplicate id, a
split spelled "held-out"). Every row is checked against the real taxonomy when it is loaded.

Row fields:
    id                    unique text id
    split                 "tune" or "heldout"
    domain                hr / legal / finance / support / engineering
    question              the user's question, as typed
    expected_frame        frame id the question should be sorted into, or null when no frame is expected
    expected_categories   taxonomy categories whose documents can answer it ([] for a question no document answers)
    needs_clarification   true when a good system should ask the user something before answering
    reference_answer      the correct answer, written by a person from the policy document (may be "")

Rows whose id starts with "EXAMPLE-" only show the format. They are never real evaluation data.
"""
import json

SPLITS = ("tune", "heldout")
FIELDS = ("id", "split", "domain", "question", "expected_frame", "expected_categories", "needs_clarification", "reference_answer")
EXAMPLE_PREFIX = "EXAMPLE-"


class QuestionError(ValueError):
    pass


def is_example(row: dict) -> bool:
    return str(row.get("id", "")).startswith(EXAMPLE_PREFIX)


def check_row(row, taxonomy, known_frames=None) -> list[str]:
    """Every problem with one row, as short messages (an empty list means the row is fine)."""
    if not isinstance(row, dict):
        return ["a row must be a JSON object"]
    problems = [f"missing field '{f}'" for f in FIELDS if f not in row]
    problems += [f"unknown field '{f}'" for f in row if f not in FIELDS]
    if problems:
        return problems

    if not isinstance(row["id"], str) or not row["id"].strip():
        problems.append("id must be non-empty text")
    if row["split"] not in SPLITS:
        problems.append(f"split must be one of {SPLITS}, found {row['split']!r}")
    if not isinstance(row["question"], str) or not row["question"].strip():
        problems.append("question must be non-empty text")
    if not isinstance(row["needs_clarification"], bool):
        problems.append("needs_clarification must be true or false")
    if not isinstance(row["reference_answer"], str):
        problems.append("reference_answer must be text (use \"\" if not written yet)")

    domain_categories = taxonomy.categories.get(row["domain"])
    if domain_categories is None:
        problems.append(f"unknown domain {row['domain']!r}")
    categories = row["expected_categories"]
    if not isinstance(categories, list) or not all(isinstance(c, str) for c in categories):
        problems.append("expected_categories must be a list of text")
    elif domain_categories is not None:
        problems += [f"category {c!r} is not in the {row['domain']} taxonomy" for c in categories if c not in domain_categories]

    frame = row["expected_frame"]
    if frame is not None:
        if not isinstance(frame, str) or not frame.startswith(f"{row['domain']}."):
            problems.append(f"expected_frame must be null or an id starting with '{row['domain']}.'")
        elif known_frames is not None and frame not in known_frames:
            problems.append(f"expected_frame {frame!r} is not in the frame menu")
    return problems


def parse_questions(lines, taxonomy, known_frames=None) -> list[dict]:
    """Rows from JSONL text lines. Blank lines and lines starting with # are skipped; all problems are reported at once."""
    rows, errors, seen = [], [], set()
    for number, line in enumerate(lines, 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            errors.append(f"line {number}: not valid JSON ({error.msg})")
            continue
        problems = check_row(row, taxonomy, known_frames)
        if not problems and row["id"] in seen:
            problems.append(f"id {row['id']!r} is used twice")
        errors += [f"line {number}: {p}" for p in problems]
        if not problems:
            seen.add(row["id"])
            rows.append(row)
    if errors:
        raise QuestionError("question set is invalid:\n  " + "\n  ".join(errors))
    return rows


def load_questions(path: str, taxonomy, known_frames=None) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return parse_questions(f.read().splitlines(), taxonomy, known_frames)
