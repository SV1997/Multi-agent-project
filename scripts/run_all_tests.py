"""Run every test suite once (Phase 1: fakes, no live services), saving per-stage .out, junit XML for pytest
stages, summary.json and summary.md under test-results/<UTC ts>/. A stage that cannot collect its tests
(missing package, bad path) is recorded as "error", not a pass or a fail.  Usage: python scripts/run_all_tests.py
"""
import datetime, json, os, re, subprocess, sys; import xml.etree.ElementTree as ET

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PY = sys.executable
TS = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
OUT = os.path.join(ROOT, "test-results", TS)
svc = lambda name: os.path.join(ROOT, "services", name)

def pytest_stage(name, targets, cwd):  # (name, command, cwd, junit path or None, shell, timeout seconds)
    junit = os.path.join(OUT, f"{name}.xml")
    return (name, [PY, "-m", "pytest", *targets.split(), "-q", f"--junitxml={junit}"], cwd, junit, False, 900)

STAGES = [  # eval/drift/tests does not exist, so it is dropped from the first stage
    pytest_stage("shared_scripts_eval", "shared scripts/tests eval/tests", ROOT),
    pytest_stage("orchestrator", "tests", svc("orchestrator")),
    pytest_stage("retrieval_service", "tests", svc("retrieval-service")),
    pytest_stage("ingestion_service", "tests", svc("ingestion_service")),
    pytest_stage("evaluation_service", "tests", svc("evaluation_service")),
    ("api_gateway", "npm test -- --ci", svc("api-gateway"), None, True, 900),
    ("taxonomy_check", [PY, "check_taxonomy.py"], ROOT, None, False, 120),
]  # frontend is skipped (no test script); recorded in run()

def counts_from_junit(path):
    """passed/failed/errors/skipped from a pytest junit file; None if it is not there."""
    if not path or not os.path.exists(path):
        return None, []
    root = ET.parse(path).getroot()
    suite = root if root.find("testsuite") is None else root.find("testsuite")
    g = lambda k: int(suite.get(k, 0))
    counts = {"passed": g("tests")-g("failures")-g("errors")-g("skipped"), "failed": g("failures"), "errors": g("errors"), "skipped": g("skipped")}
    fails = [f"{c.get('classname','')}::{c.get('name','')}: {((n.get('message') or (n.text or '').strip()).splitlines() or [''])[0][:200]}"
             for c in root.iter("testcase")
             for n in [c.find("failure") if c.find("failure") is not None else c.find("error")] if n is not None]
    return counts, fails

def counts_from_text(out):
    """Jest counts and failing lines from text output (no junit). (None, [...]) when no Jest tally is present."""
    m = re.search(r"^Tests:\s+(?:(\d+) failed, )?.*?(\d+) total", out, re.M)
    fails = [ln.strip().replace("●", "*") for ln in out.splitlines()
             if ln.startswith("FAIL ") or ln.lstrip().startswith("●")][:40]
    if not m:
        return None, fails
    failed = int(m.group(1) or 0)
    return {"passed": int(m.group(2)) - failed, "failed": failed, "errors": 0, "skipped": 0}, fails

def run_stage(name, cmd, cwd, junit, shell, timeout):
    start = datetime.datetime.now()
    try:   # force utf-8: a stage's output can carry bytes the Windows locale codec cannot decode
        proc = subprocess.run(cmd, cwd=cwd, shell=shell, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=timeout)
        out, code, timed = (proc.stdout or "") + (proc.stderr or ""), proc.returncode, False
    except subprocess.TimeoutExpired as e:
        out = "".join(p if isinstance(p, str) else (p.decode("utf-8", "replace") if p else "") for p in (e.stdout, e.stderr))
        code, timed = None, True
    seconds = round((datetime.datetime.now() - start).total_seconds(), 1)
    with open(os.path.join(OUT, f"{name}.out"), "w", encoding="utf-8", errors="replace") as f:
        f.write(out or "")
    counts, fails = counts_from_junit(junit)
    if counts is None and junit is None:        # jest / the taxonomy script write no junit, so read the text
        counts, fails = counts_from_text(out)
    if timed:
        status = "timeout"
    elif counts is None:
        status = "passed" if code == 0 else "failed"
    else:
        status = "error" if counts["errors"] else ("failed" if counts["failed"] else "passed")
    return {"stage": name, "status": status, "seconds": seconds, "returncode": code, "counts": counts, "failures": fails}

def run():
    os.makedirs(OUT, exist_ok=True)
    results = []
    for stage in STAGES:
        print(f"==> {stage[0]}")
        results.append(run_stage(*stage))
    results.append({"stage": "frontend", "status": "skipped", "seconds": 0, "returncode": None, "counts": None,
                    "failures": [], "skip_reason": "no test script in package.json; no *.test/*.spec files"})
    return results

def write_summary(results):
    with open(os.path.join(OUT, "summary.json"), "w", encoding="utf-8") as f:
        json.dump({"timestamp_utc": TS, "root": ROOT, "results": results}, f, indent=2)
    rows = ["# Test run " + TS, "", "| stage | passed | failed | errors | skipped | seconds | status |",
            "|---|---|---|---|---|---|---|"]
    for r in results:
        c = r["counts"] or {}
        rows.append(f"| {r['stage']} | {c.get('passed','-')} | {c.get('failed','-')} | {c.get('errors','-')} | {c.get('skipped','-')} | {r['seconds']} | **{r['status']}** |")
    named = [f"- `{r['stage']}` {line}" for r in results for line in r["failures"]]
    rows += ["", "## First line of every failure"] + (named or ["- none"])
    with open(os.path.join(OUT, "summary.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(rows) + "\n")
    print("\n".join(rows) + f"\n\nSaved under {OUT}")

if __name__ == "__main__":
    write_summary(run())
