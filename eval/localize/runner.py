"""Runs the evaluation question set against a running orchestrator and compares the LOCALIZE levels.

Why this file exists: the examiner's notes were about whether sorting questions into categories helps. This is
the experiment. Three commands:
    run      asks every question of the set once at ONE level and stores what came back (answer, cited sources,
             the frame decision) in results/<level>.json
    run-all  does that for all four levels in turn (switching the stack between them), then writes the combined
             table as results/comparison.csv and results/comparison.md
    report   reads the stored results of the levels and prints / writes the same table (see metrics.py)

Problem it solves: LOCALIZE is a setting of the running services, so one process cannot switch it by itself.
`run-all --switch compose` restarts the two services that read it; `--switch manual` asks you to. The files in
results/ hold one level each and the table compares them. Nothing is ever filled in by this file: a number
appears only if it was measured. A question whose request fails (timeout, error, paused for review) is stored
as a failure, named on the console and counted in the table - never dropped silently.

Windows / uv, from the repository root (the stack must be up, with LOCALIZE set to the level you pass):
    uv run python eval/localize/runner.py run --level off --questions eval/localize/questions.jsonl
    uv run python eval/localize/runner.py run --level filter --questions eval/localize/questions.jsonl
    uv run python eval/localize/runner.py report --questions eval/localize/questions.jsonl

All four levels in one command (--switch compose restarts the two services per level, --switch manual asks you to),
then the combined table results/comparison.csv and results/comparison.md:
    uv run python eval/localize/runner.py run-all --questions eval/localize/questions.jsonl --switch compose

Check the pipeline and the table format with no services, on made-up answers (written to results_dryrun/, labelled FAKE):
    uv run python eval/localize/runner.py run-all --dry-run --questions eval/localize/questions.example.jsonl

A question set must contain both "tune" and "heldout" rows, or every command refuses to run.
The secret is read from INTERNAL_SHARED_SECRET (the same value the orchestrator uses), never from the command line.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
for path in (HERE, ROOT):
    if path not in sys.path:
        sys.path.insert(0, path)

import comparison  # noqa: E402
from fakes import FakeClient  # noqa: E402
from metrics import compute  # noqa: E402
from questions import QuestionError, is_example, load_questions, require_both_splits  # noqa: E402

LEVELS = ("off", "filter", "prompt", "full")
DOMAINS = ["hr", "legal", "finance", "support", "engineering"]
RESULTS_DIR = os.path.join(HERE, "results")
DRYRUN_DIR = os.path.join(HERE, "results_dryrun")
DRYRUN_BANNER = "DRY RUN: every number below comes from a FAKE client and says nothing about the real system."


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


def failure_summary(results: dict, level: str) -> list[str]:
    """Lines naming every question that failed at this level, so a failure is never silent. Empty when none failed."""
    failed = {qid: r["error"] for qid, r in results.items() if r.get("error")}
    if not failed:
        return []
    lines = [f"WARNING: {len(failed)} of {len(results)} questions FAILED at level {level}; they are counted as failed "
             "(left out of the rates, shown in the 'requests that failed' row):"]
    lines += [f"  {qid}: {error}" for qid, error in failed.items()]
    return lines


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


def save_results(out_dir: str, level: str, fingerprint: str, results: dict, fake: bool = False) -> str:
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{level}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"level": level, "questions": fingerprint, "fake": fake, "results": results}, f, indent=1)
    return path


def stored_as_fake(out_dir: str) -> bool:
    """True when any stored level file was written by a dry run."""
    for level in LEVELS:
        path = os.path.join(out_dir, f"{level}.json")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                if json.load(f).get("fake"):
                    return True
    return False


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
    """Side-by-side table, one column per level, then the tune / heldout split and the gap."""
    return comparison.to_text(reports)


def load_set(args):
    from shared.taxonomy.taxonomy import load_taxonomy
    taxonomy = load_taxonomy()
    rows = load_questions(args.questions, taxonomy, known_frame_ids(taxonomy))
    require_both_splits(rows)
    if any(is_example(r) for r in rows):
        print("WARNING: the set contains EXAMPLE rows. They only show the format; do not report numbers from them.")
    return taxonomy, rows


def wait_until_healthy(url: str, seconds: int = 120) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url.rstrip("/") + "/health", timeout=5):
                return True
        except Exception:
            time.sleep(3)
    return False


def switch_with_compose(level: str, url: str) -> bool:
    """Recreate the two services that read LOCALIZE with the new value (no rebuild: it is a runtime setting)."""
    env = {**os.environ, "LOCALIZE": level}
    done = subprocess.run(["docker", "compose", "up", "-d", "--no-deps", "orchestrator", "retrieval-service"],
                          cwd=ROOT, env=env)
    return done.returncode == 0 and wait_until_healthy(url)


def switch_manually(level: str, url: str) -> bool:
    print(f"\nSet LOCALIZE={level} on the orchestrator and the retrieval service and wait until they are up, then press Enter.")
    input()
    return True


def run_all(rows, taxonomy, levels, make_ask, switch, out_dir, fingerprint, fake=False) -> list[dict]:
    """Every level in turn over the same rows: switch the stack, ask all questions, store one result file per level.

    make_ask(level) gives the function that asks one question; switch(level) returns False when the stack could not
    be switched (None means nothing to switch, as in a dry run). Returns the metric reports of the levels that ran."""
    reports = []
    for level in levels:
        if switch is not None and not switch(level):
            print(f"Could not switch the stack to LOCALIZE={level}; stopping. Levels already stored stay in {out_dir}.")
            break
        results = run_questions(rows, make_ask(level))
        for line in failure_summary(results, level):
            print(line)
        for warning in level_warnings(results, level):
            print("WARNING:", warning)
        print("stored", save_results(out_dir, level, fingerprint, results, fake))
        reports.append(compute(rows, results, taxonomy, level))
    return reports


def finish_report(reports, out_dir, fake):
    print(comparison.to_text(reports))
    csv_path, md_path = comparison.write_comparison(reports, out_dir, banner=DRYRUN_BANNER if fake else None)
    print(f"\nwrote {csv_path}\nwrote {md_path}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="ask every question once at one level and store the results")
    run.add_argument("--level", required=True, choices=LEVELS, help="the LOCALIZE value the stack is running with")
    run.add_argument("--url", default="http://localhost:8003", help="orchestrator base URL")
    run.add_argument("--email", default=os.getenv("EVAL_EMPLOYEE_EMAIL", ""), help="employee e-mail sent with each question")
    every = sub.add_parser("run-all", help="run the levels over one question file and write the comparison table")
    every.add_argument("--url", default="http://localhost:8003", help="orchestrator base URL")
    every.add_argument("--email", default=os.getenv("EVAL_EMPLOYEE_EMAIL", ""))
    every.add_argument("--levels", nargs="+", choices=LEVELS, default=list(LEVELS))
    every.add_argument("--dry-run", action="store_true",
                       help="fake client: no services and no secret; results go to results_dryrun/ and are labelled FAKE")
    every.add_argument("--switch", choices=("compose", "manual"),
                       help="how LOCALIZE is changed between levels: 'compose' restarts the two services with docker "
                            "compose, 'manual' waits for you to do it (required unless --dry-run)")
    for p in (run, every, sub.add_parser("report", help="compare the stored runs")):
        p.add_argument("--questions", required=True, help="the JSONL question set")
        p.add_argument("--out-dir", default=None, help="where results go (default results/, or results_dryrun/ for --dry-run)")
    args = parser.parse_args(argv)
    args.out_dir = args.out_dir or (DRYRUN_DIR if getattr(args, "dry_run", False) else RESULTS_DIR)

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
        for line in failure_summary(results, args.level):
            print(line)
        for warning in level_warnings(results, args.level):
            print("WARNING:", warning)
        print("stored", save_results(args.out_dir, args.level, fingerprint, results))
        return 0

    if args.command == "run-all":
        if args.dry_run:
            print(DRYRUN_BANNER)
            reports = run_all(rows, taxonomy, args.levels, lambda level: FakeClient(level, taxonomy), None,
                              args.out_dir, fingerprint, fake=True)
            finish_report(reports, args.out_dir, fake=True)
            return 0
        secret = os.getenv("INTERNAL_SHARED_SECRET")
        if not secret:
            print("Set INTERNAL_SHARED_SECRET to the orchestrator's internal secret first.")
            return 2
        if not args.switch:
            print("run-all changes LOCALIZE between levels. Say how with --switch compose (restart the two services "
                  "with docker compose) or --switch manual (you change it when asked), or use --dry-run.")
            return 2
        if args.switch == "compose":
            def switch(level):
                return switch_with_compose(level, args.url)
        else:
            def switch(level):
                return switch_manually(level, args.url)
        reports = run_all(rows, taxonomy, args.levels,
                          lambda level: (lambda row: post_query(args.url, secret, row, args.email)),
                          switch, args.out_dir, fingerprint)
        if not reports:
            return 1
        finish_report(reports, args.out_dir, fake=False)
        return 0

    stored = load_all_results(args.out_dir, fingerprint)
    if not stored:
        print("No stored runs for this question set. Use the run command first.")
        return 1
    reports = [compute(rows, stored[level], taxonomy, level) for level in LEVELS if level in stored]
    finish_report(reports, args.out_dir, fake=stored_as_fake(args.out_dir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
