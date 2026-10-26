"""Runs the evaluation question set against a running orchestrator and compares the LOCALIZE levels.

Why this file exists: the examiner's notes were about whether sorting questions into categories helps. This is
the experiment. Two steps:
    run     asks every question of the set once and stores what came back (answer, cited sources, the frame
            decision) in results/<level>.json
    report  reads the stored results of the levels and prints the metrics side by side (see metrics.py)

Problem it solves: LOCALIZE is a setting of the running services, so one process cannot switch it. You start the
stack with one level, run, change the level, restart, run again - the files in results/ then hold one level each
and `report` compares them. Nothing is ever filled in by this file: a number appears only if it was measured.

Windows / uv, from the repository root (the stack must be up, with LOCALIZE set to the level you pass):
    uv run python eval/localize/runner.py run --level off --questions eval/localize/questions.jsonl
    uv run python eval/localize/runner.py run --level filter --questions eval/localize/questions.jsonl
    uv run python eval/localize/runner.py report --questions eval/localize/questions.jsonl

The secret is read from INTERNAL_SHARED_SECRET (the same value the orchestrator uses), never from the command line.
"""
import argparse
import hashlib
import json
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
for path in (HERE, ROOT):
    if path not in sys.path:
        sys.path.insert(0, path)

from metrics import METRICS, compute, percent  # noqa: E402
from questions import QuestionError, is_example, load_questions  # noqa: E402

LEVELS = ("off", "filter", "prompt", "full")
DOMAINS = ["hr", "legal", "finance", "support", "engineering"]
RESULTS_DIR = os.path.join(HERE, "results")


def post_query(url: str, secret: str, row: dict, email: str, timeout: int = 180) -> dict:
    """One question to the orchestrator's /query endpoint, as a new conversation. Returns the JSON body."""
    body = json.dumps({"query": row["question"], "allowed_namespace": DOMAINS, "employee_email": email}).encode()
    request = urllib.request.Request(url.rstrip("/") + "/api/v1/query", data=body, method="POST",
                                     headers={"Content-Type": "application/json", "x-internal-secret": secret})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


def run_questions(rows: list[dict], ask) -> dict:
    """Ask every question with `ask(row) -> dict` and keep a compact result per id. A failure is recorded, not raised."""
    results = {}
    for row in rows:
        try:
            body = ask(row)
        except Exception as error:                                          # one bad question must not lose the others
            results[row["id"]] = {"error": f"{type(error).__name__}: {error}"}
            continue
        if body.get("status") == "paused_for_review":
            results[row["id"]] = {"error": "paused for human review"}
            continue
        results[row["id"]] = {"answer": body.get("answer"), "sources": body.get("sources") or [],
                              "confidence": body.get("confidence"), "debug": body.get("debug")}
    return results


def level_warnings(results: dict, level: str) -> list[str]:
    """Signs that the server was not running at the level the user said (the response never names its level)."""
    answered = [r for r in results.values() if not r.get("error")]
    framed = [r for r in answered if (r.get("debug") or {}).get("frame_id")]
    if level == "off" and framed:
        return [f"{len(framed)} answers carry a frame, so the server is NOT running with LOCALIZE=off"]
    if level != "off" and answered and not framed:
        return [f"no answer carries a frame, so the server is probably NOT running with LOCALIZE={level}"]
    return []


def questions_fingerprint(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()[:12]


def known_frame_ids(taxonomy):
    """Frame ids of the real menu, so a typo in expected_frame is caught. None when the orchestrator code cannot be loaded."""
    try:
        sys.path.insert(0, os.path.join(ROOT, "services", "orchestrator"))
        from app.graph.frames.registry import load_registry
        registry = load_registry(taxonomy)
        return {frame.frame_id for domain in taxonomy.categories for frame in registry.menu(domain)}
    except Exception as error:
        print(f"note: frame ids were not checked ({type(error).__name__}: {error})")
        return None


def save_results(out_dir: str, level: str, fingerprint: str, results: dict) -> str:
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{level}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"level": level, "questions": fingerprint, "results": results}, f, indent=1)
    return path


def load_all_results(out_dir: str, fingerprint: str) -> dict:
    """{level: results} for the levels that have a stored run of THIS question set."""
    found, stale = {}, []
    for level in LEVELS:
        path = os.path.join(out_dir, f"{level}.json")
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if data.get("questions") == fingerprint:
            found[level] = data["results"]
        else:
            stale.append(level)
    if stale:
        print(f"skipped (run with a different question set, run them again): {', '.join(stale)}")
    return found


def format_report(reports: list[dict]) -> str:
    """Side-by-side table, one column per level, then the tune / heldout split."""
    names = {"wrong_category_citation": "wrong-category citations", "frame_accuracy": "frame accuracy",
             "clarification_correct": "clarification correct", "fallback_rate": "fallback (widened) rate"}
    width = 26
    head = "".ljust(width) + "".join(r["level"].rjust(18) for r in reports)
    lines = []
    for part, title in (("all", "ALL QUESTIONS"), ("tune", "TUNE QUESTIONS"), ("heldout", "HELD-OUT QUESTIONS")):
        lines += ["", title, head]
        lines.append("questions".ljust(width) + "".join(str(r[part]["questions"]).rjust(18) for r in reports))
        for name in METRICS:
            cells = []
            for r in reports:
                m = r[part][name]
                cells.append(f"{percent(m['value'])} (n={m['n']})".rjust(18))
            lines.append(names[name].ljust(width) + "".join(cells))
    lines += ["", "GAP (tune minus held-out; a large positive gap means the frames fit the tuning questions)", head]
    for name in METRICS:
        gaps = ["n/a" if r["gap"][name] is None else f"{r['gap'][name] * 100:+.1f} pts" for r in reports]
        lines.append(names[name].ljust(width) + "".join(g.rjust(18) for g in gaps))
    unjudged = ["cited sources not judged".ljust(width) + "".join(
        str(r["all"]["wrong_category_citation"]["unjudged"]).rjust(18) for r in reports)]
    errors = ["requests that failed".ljust(width) + "".join(str(r["errors"]).rjust(18) for r in reports)]
    return "\n".join(lines + [""] + unjudged + errors)


def load_set(args):
    from shared.taxonomy.taxonomy import load_taxonomy
    taxonomy = load_taxonomy()
    rows = load_questions(args.questions, taxonomy, known_frame_ids(taxonomy))
    if any(is_example(r) for r in rows):
        print("WARNING: the set contains EXAMPLE rows. They only show the format; do not report numbers from them.")
    return taxonomy, rows


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="ask every question once and store the results")
    run.add_argument("--level", required=True, choices=LEVELS, help="the LOCALIZE value the stack is running with")
    run.add_argument("--url", default="http://localhost:8003", help="orchestrator base URL")
    run.add_argument("--email", default=os.getenv("EVAL_EMPLOYEE_EMAIL", ""), help="employee e-mail sent with each question")
    for p in (run, sub.add_parser("report", help="compare the stored runs")):
        p.add_argument("--questions", required=True, help="the JSONL question set")
        p.add_argument("--out-dir", default=RESULTS_DIR)
    args = parser.parse_args(argv)

    try:
        taxonomy, rows = load_set(args)
    except (QuestionError, OSError) as error:
        print(error)
        return 2
    fingerprint = questions_fingerprint(args.questions)

    if args.command == "run":
        secret = os.getenv("INTERNAL_SHARED_SECRET")
        if not secret:
            print("Set INTERNAL_SHARED_SECRET to the orchestrator's internal secret first.")
            return 2
        results = run_questions(rows, lambda row: post_query(args.url, secret, row, args.email))
        for warning in level_warnings(results, args.level):
            print("WARNING:", warning)
        print("stored", save_results(args.out_dir, args.level, fingerprint, results))
        return 0

    stored = load_all_results(args.out_dir, fingerprint)
    if not stored:
        print("No stored runs for this question set. Use the run command first.")
        return 1
    print(format_report([compute(rows, stored[level], taxonomy, level) for level in LEVELS if level in stored]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
