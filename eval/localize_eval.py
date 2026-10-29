"""Does query localization help? Two checks, each reported by split and by label precision.

  frames    needs only the Groq key. For each question: which frame is chosen, is the expected category among the
            categories that frame searches (after the DAG walk), and how many categories is that.
  answers   needs the running stack. Sends each question to the orchestrator and reports the share of cited
            documents that fall outside the expected category. Run it twice: stack on, then stack off.

Rows are split two ways, and the ways are never averaged together:
  tune / test         tune the frames on "tune", report "test"
  precise / coarse    precise = every document of the expected category carries 2 categories or fewer in the yaml;
                      coarse = some document carries 3 or more, so it matches almost any category filter

Question file, one JSON object per line:
  {"question": "...", "domain": "hr", "expected_category": "casual_and_sick_leave", "split": "tune"}

  uv run python eval/localize_eval.py frames  --questions eval/questions.jsonl
  uv run python eval/localize_eval.py answers --questions eval/questions.jsonl --setting on    (then --setting off)
  uv run python eval/localize_eval.py report  --questions eval/questions.jsonl
"""
import argparse
import json
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "services", "orchestrator"))      # so `app.graph.frames` imports as in the service

from shared.taxonomy.taxonomy import DOMAINS, expand_with_descendants, load_taxonomy  # noqa: E402

FIELDS = ("question", "domain", "expected_category", "split")


def load_questions(path: str, taxonomy) -> list[dict]:
    """A bad line must stop the run, or a typo would quietly change the numbers."""
    rows, problems = [], []
    with open(path, encoding="utf-8") as file:
        for number, line in enumerate(file, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except ValueError:
                problems.append(f"line {number}: not valid JSON")
                continue
            if not isinstance(row, dict) or set(row) != set(FIELDS):
                problems.append(f"line {number}: the fields must be exactly {', '.join(FIELDS)}")
            elif row["split"] not in ("tune", "test"):
                problems.append(f"line {number}: split must be 'tune' or 'test'")
            elif row["expected_category"] not in taxonomy.categories.get(row["domain"], {}):
                problems.append(f"line {number}: '{row['expected_category']}' is not a category of '{row['domain']}'")
            else:
                rows.append(row)
    if not problems and {row["split"] for row in rows} != {"tune", "test"}:
        problems.append("the file needs both 'tune' and 'test' lines: tune on one, report the other")
    if problems:
        raise ValueError("question file is invalid:\n  " + "\n  ".join(problems))
    return rows


def label_precision(taxonomy, domain: str, category: str) -> str:
    """Localizing can only narrow the search when the category's documents carry few labels, so rows are grouped by that."""
    wanted = set(expand_with_descendants(taxonomy, domain, [category]))
    sizes = [len(categories) for categories in taxonomy.documents[domain].values() if wanted & set(categories)]
    if not sizes:
        return "no document"
    return "coarse" if max(sizes) >= 3 else "precise"


def pct(part: int, whole: int) -> str:
    return f"{100 * part / whole:.0f}%" if whole else "n/a"


def table(records: list[dict], columns: list) -> str:
    """One row per split and per precision group; precise and coarse are printed apart, never averaged."""
    lines = ["| split | documents | n | " + " | ".join(name for name, _ in columns) + " |", "|" + "---|" * (3 + len(columns))]
    for split in ("tune", "test"):
        for group in ("precise", "coarse", "no document"):
            part = [r for r in records if r["split"] == split and r["group"] == group]
            if part or group != "no document":
                lines.append(f"| {split} | {group} | {len(part)} | " + " | ".join(function(part) for _, function in columns) + " |")
    return "\n".join(lines)


def frame_records(rows: list[dict], taxonomy, choose) -> list[dict]:
    """Runs the real frame choice and the real DAG walk on every question."""
    from app.graph.frames.registry import load_registry
    registry, records = load_registry(taxonomy), []
    for row in rows:
        frame = choose(registry.get(row["domain"], []), row["domain"], row["question"])
        expanded = expand_with_descendants(taxonomy, row["domain"], frame.categories) if frame else []
        records.append({**row, "group": label_precision(taxonomy, row["domain"], row["expected_category"]),
                        "hit": row["expected_category"] in expanded, "no_frame": frame is None,
                        "searched": len(expanded) or len(taxonomy.categories[row["domain"]])})   # no frame = whole domain
    return records


FRAME_COLUMNS = [
    ("expected category searched", lambda part: pct(sum(r["hit"] for r in part), len(part))),
    ("no frame", lambda part: str(sum(r["no_frame"] for r in part))),
    ("mean categories searched", lambda part: f"{sum(r['searched'] for r in part) / len(part):.1f}" if part else "n/a"),
]
ANSWER_COLUMNS = [
    ("failed", lambda part: str(sum(r["failed"] for r in part))),
    ("sources cited", lambda part: str(sum(r["judged"] for r in part))),
    ("outside expected category", lambda part: pct(sum(r["outside"] for r in part), sum(r["judged"] for r in part))),
    ("unjudged", lambda part: str(sum(r["unjudged"] for r in part))),
]


def answer_records(rows: list[dict], results: list[dict], taxonomy) -> list[dict]:
    """A cited document is outside when it shares no category with the expected one (or anything below it)."""
    if [r["question"] for r in rows] != [r["question"] for r in results]:
        raise ValueError("the stored results are for a different question file; run `answers` again")
    records = []
    for row, result in zip(rows, results):
        expected = set(expand_with_descendants(taxonomy, row["domain"], [row["expected_category"]]))
        counts = {"outside": 0, "judged": 0, "unjudged": 0}
        for source in dict.fromkeys(result.get("sources") or []):          # each distinct source once per question
            categories = set(taxonomy.for_chunk(row["domain"], str(source)))
            if categories == {"uncategorized"}:
                counts["unjudged"] += 1
            else:
                counts["judged"] += 1
                counts["outside"] += not (categories & expected)
        records.append({**row, **counts, "group": label_precision(taxonomy, row["domain"], row["expected_category"]),
                        "failed": "error" in result})
    return records


def get_json(url: str, body=None, secret=None) -> dict:
    headers = {"Content-Type": "application/json", "x-internal-secret": secret or ""}
    request = urllib.request.Request(url, data=body, headers=headers, method="POST" if body else "GET")
    with urllib.request.urlopen(request, timeout=180) as response:
        return json.loads(response.read())


def run_answers(rows: list[dict], url: str, secret: str, email: str) -> list[dict]:
    """One failed question is recorded, not raised, so the others are kept."""
    results = []
    for row in rows:
        body = json.dumps({"query": row["question"], "allowed_namespace": list(DOMAINS), "employee_email": email}).encode()
        try:
            results.append({"question": row["question"], "sources": get_json(url + "/api/v1/query", body, secret).get("sources") or []})
        except Exception as error:
            results.append({"question": row["question"], "error": f"{type(error).__name__}: {error}"})
    return results


def results_path(setting: str) -> str:
    return os.path.join(HERE, "results", f"answers_{setting}.json")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate query localization.")
    parser.add_argument("mode", choices=["frames", "answers", "report"])
    parser.add_argument("--questions", required=True)
    parser.add_argument("--setting", choices=["on", "off"], help="answers mode: the LOCALIZE value the stack runs with")
    parser.add_argument("--url", default="http://localhost:8003", help="orchestrator")
    parser.add_argument("--retrieval-url", default="http://localhost:8001", help="retrieval service")
    parser.add_argument("--email", default=os.getenv("EVAL_EMPLOYEE_EMAIL", ""))
    args = parser.parse_args(argv)
    taxonomy = load_taxonomy()
    try:
        rows = load_questions(args.questions, taxonomy)
    except ValueError as error:
        print(error)
        return 2
    if args.mode == "frames":
        from app.graph.frames.node import choose_frame
        print(table(frame_records(rows, taxonomy, choose_frame), FRAME_COLUMNS))
    elif args.mode == "answers":
        secret = os.getenv("INTERNAL_SHARED_SECRET")
        if not (args.setting and secret):
            print("answers mode needs --setting on|off and INTERNAL_SHARED_SECRET set to the orchestrator's secret")
            return 2
        for url in (args.url, args.retrieval_url):             # a run labelled 'on' against a stack that is off would mislead
            try:
                running = get_json(url + "/health").get("localize")
            except OSError as error:
                print(f"cannot reach {url}: {error}")
                return 2
            if running != args.setting:
                print(f"{url} is running with LOCALIZE={running}, not {args.setting}; restart the stack first")
                return 2
        os.makedirs(os.path.dirname(results_path("on")), exist_ok=True)
        with open(results_path(args.setting), "w", encoding="utf-8") as file:
            json.dump(run_answers(rows, args.url, secret, args.email), file, indent=1)
        print("stored", results_path(args.setting))
    else:
        stored = [setting for setting in ("on", "off") if os.path.exists(results_path(setting))]
        for setting in stored:
            with open(results_path(setting), encoding="utf-8") as file:
                print(f"LOCALIZE={setting}\n" + table(answer_records(rows, json.load(file), taxonomy), ANSWER_COLUMNS) + "\n")
        if not stored:
            print("No stored results. Run `answers` once with --setting on and once with --setting off.")
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
