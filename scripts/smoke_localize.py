"""Smoke test of localized search through the running gateway: three questions, each LOCALIZE level.

Why this file exists: every test so far uses fakes. This is the first check that the real chain (gateway ->
orchestrator -> retrieval -> Pinecone / BM25) shows the frame, the categories, the widening level and the
clarifying question the code is supposed to produce. It is a smoke test, not an evaluation: it sends three
questions and prints what came back. It scores nothing and proves nothing about quality.

The three questions (override the text with --in-domain / --ambiguous / --outside):
    in-domain   a clear question the policy documents should answer
    ambiguous   a question that lacks a detail, so LOCALIZE=full should ask the user a clarifying question
    outside     a question the corpus cannot answer, so the system should decline or cite nothing

Setup (PowerShell, from the repository root; nothing is hard-coded, both values come from the environment):
    $env:GATEWAY_URL   = "http://localhost:3000"          # the gateway's base URL
    $env:GATEWAY_TOKEN = "<access token from POST /auth/login>"

    uv run python scripts/smoke_localize.py                          # asks at whatever level the stack is running at
    uv run python scripts/smoke_localize.py --levels full            # same, labelled "full" (you set LOCALIZE yourself)
    uv run python scripts/smoke_localize.py --levels off filter prompt full --switch compose
                                        # restarts orchestrator + retrieval-service with each LOCALIZE value first

LOCALIZE is a setting of the running services, so the script cannot change it on its own: --switch compose runs
`docker compose up -d --no-deps orchestrator retrieval-service` with LOCALIZE set, --switch manual waits for you.
The gateway rate-limits requests; if you see HTTP 429, wait a minute and run again with fewer --levels.
Exit codes: 0 finished, 2 gateway not reachable / not configured, 1 a level could not be set.
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request
import uuid

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "eval", "localize"))

LEVELS = ("off", "filter", "prompt", "full")
DEFAULT_QUESTIONS = {
    "in-domain": "How many days of earned leave do I get?",
    "ambiguous": "How many days of leave do I get?",
    "outside": "What is the capital city of Australia?",
}
EXPECTED = {
    "in-domain": "an answer that cites at least one source",
    "ambiguous": "a clarifying question at level full; an ordinary answer below it",
    "outside": "a refusal, or an answer that cites nothing",
}


class GatewayUnreachable(Exception):
    pass


def post_query(base_url: str, token: str, question: str, timeout: int = 180) -> dict:
    """POST /query on the gateway, the same call the frontend's non-streaming path makes. Returns the JSON body."""
    body = json.dumps({"query": question, "sessionId": "smoke-localize", "turnId": str(uuid.uuid4())}).encode()
    request = urllib.request.Request(base_url.rstrip("/") + "/query", data=body, method="POST", headers={
        "Content-Type": "application/json", "Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"gateway answered HTTP {error.code}" + (" (rate limit: wait and retry)" if error.code == 429
                           else " (token expired or wrong?)" if error.code == 401 else "")) from None
    except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as error:
        raise GatewayUnreachable(str(getattr(error, "reason", error))) from None


def check_reachable(base_url: str) -> None:
    """Fail early and clearly when nothing answers at the gateway URL."""
    try:
        urllib.request.urlopen(base_url.rstrip("/") + "/health", timeout=10).close()
    except urllib.error.HTTPError:
        return                                               # something answered, even if it was an error page
    except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as error:
        raise GatewayUnreachable(str(getattr(error, "reason", error))) from None


def cited_categories(body: dict, taxonomy) -> tuple[list[tuple[str, list[str]]], str]:
    """[(source, categories)] for the cited chunks, and where the categories came from.

    With localization on, the answer's debug trace lists the evidence with the categories stored on each chunk.
    Without it (LOCALIZE=off, or no frame) the categories are looked up in the taxonomy from the source name; a
    document whose chunks are labelled one by one cannot be resolved that way and shows "(mixed document)"."""
    nodes = ((body.get("debug") or {}).get("query_dag") or {}).get("nodes") or []
    evidence = [n for n in nodes if n.get("type") == "evidence"]
    if evidence:
        return [(str(n.get("label")), list(n.get("categories") or [])) for n in evidence], "chunk labels (debug trace)"
    out = []
    domain = body.get("domain")
    for source in body.get("sources") or []:
        if taxonomy is None or domain not in taxonomy.categories:
            out.append((str(source), []))
        elif taxonomy.is_mixed(domain, str(source)):
            out.append((str(source), ["(mixed document)"]))
        else:
            out.append((str(source), list(taxonomy.for_chunk(domain, str(source)))))
    return out, "taxonomy lookup by source name" if out else "no citations"


def summarize(kind: str, level: str, body: dict, taxonomy) -> dict:
    """The facts printed for one question, plus whether they match what the question is meant to show."""
    if body.get("status") == "paused_for_review" or body.get("threadId"):
        return {"kind": kind, "level": level, "paused": True}
    debug = body.get("debug") or {}
    cited, origin = cited_categories(body, taxonomy)
    asked = bool(debug.get("clarifying_question"))
    refused = "couldn't find enough relevant information" in str(body.get("answer", "")).lower()
    if kind == "in-domain":
        matches = bool(cited)
    elif kind == "ambiguous":
        matches = (asked if level == "full" else not asked) if level in LEVELS else None     # None: level unknown
    else:
        matches = refused or not cited
    return {"kind": kind, "level": level, "paused": False, "frame": debug.get("frame_id"),
            "categories": debug.get("categories"), "fallback_level": debug.get("fallback_level"),
            "levels_tried": debug.get("levels_tried"), "asked": asked,
            "clarifying_question": debug.get("clarifying_question"), "cited": cited, "cited_from": origin,
            "answer": str(body.get("answer", "")), "matches": matches}


def format_summary(s: dict, question: str) -> str:
    head = f"[{s['level']}] {s['kind']}: {question}"
    if s["paused"]:
        return head + "\n  paused for human review; no answer to inspect (ask again or approve it in the admin view)"
    lines = [head,
             f"  frame:            {s['frame'] or '(none: no frame was used)'}",
             f"  categories:       {s['categories'] if s['categories'] else '(none)'}",
             f"  fallback_level:   {'(none)' if s['fallback_level'] is None else s['fallback_level']}"
             f"   levels tried: {s['levels_tried'] if s['levels_tried'] else '(none)'}",
             f"  clarifying asked: {'YES: ' + str(s['clarifying_question']) if s['asked'] else 'no'}",
             f"  cited chunks:     {len(s['cited'])} ({s['cited_from']})"]
    lines += [f"      {source[-60:]:60s} {cats}" for source, cats in s["cited"]]
    lines.append(f"  answer:           {' '.join(s['answer'].split())[:140]}")
    lines.append(f"  expected: {EXPECTED[s['kind']]} -> "
                 + {True: "as expected", False: "NOT as expected, look at this one", None: "not checked (level not named)"}[s["matches"]])
    return "\n".join(lines)


def run_smoke(ask, questions: dict, levels, switch, taxonomy, out=print) -> int:
    """For each level: switch the stack (if asked to), then send each question. `ask(question) -> body`.
    Returns 0, or 1 when a level could not be set."""
    for level in levels:
        out(f"\n===== LOCALIZE = {level} =====")
        if switch is not None and not switch(level):
            out(f"Could not switch the stack to LOCALIZE={level}; stopping.")
            return 1
        for kind, question in questions.items():
            try:
                body = ask(question)
            except RuntimeError as error:
                out(f"[{level}] {kind}: {question}\n  FAILED: {error}")
                continue
            out(format_summary(summarize(kind, level, body, taxonomy), question))
    return 0


def build_parser():
    ap = argparse.ArgumentParser(description="Send three questions through the running gateway at each LOCALIZE level.")
    ap.add_argument("--levels", nargs="+", choices=LEVELS, default=None,
                    help="levels to run (default: one pass, labelled with LOCALIZE_LEVEL or 'current')")
    ap.add_argument("--switch", choices=("compose", "manual"),
                    help="change LOCALIZE between levels: restart the two services with docker compose, or wait for you")
    ap.add_argument("--in-domain", default=DEFAULT_QUESTIONS["in-domain"])
    ap.add_argument("--ambiguous", default=DEFAULT_QUESTIONS["ambiguous"])
    ap.add_argument("--outside", default=DEFAULT_QUESTIONS["outside"])
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    url, token = os.getenv("GATEWAY_URL"), os.getenv("GATEWAY_TOKEN")
    if not url or not token:
        print("Set GATEWAY_URL (for example http://localhost:3000) and GATEWAY_TOKEN (an access token from POST /auth/login) first.")
        return 2
    if len(args.levels or []) > 1 and not args.switch:
        print("More than one level needs --switch compose (restart the services for each) or --switch manual.")
        return 2
    try:
        check_reachable(url)
    except GatewayUnreachable as error:
        print(f"Cannot reach the gateway at {url} ({error}).\n"
              "Start the stack first:  $env:LOCALIZE = \"full\"; docker compose up -d --build   (then wait for it to be healthy)")
        return 2

    from shared.taxonomy.taxonomy import load_taxonomy
    try:
        taxonomy = load_taxonomy()
    except Exception:
        taxonomy = None

    switch = None
    if args.switch:
        import runner
        switch = (lambda level: runner.switch_with_compose(level, url)) if args.switch == "compose" \
            else (lambda level: runner.switch_manually(level, url))
    levels = args.levels or [os.getenv("LOCALIZE_LEVEL", "current")]
    questions = {"in-domain": args.in_domain, "ambiguous": args.ambiguous, "outside": args.outside}
    try:
        return run_smoke(lambda q: post_query(url, token, q), questions, levels, switch, taxonomy)
    except GatewayUnreachable as error:
        print(f"Lost the gateway at {url} ({error}).")
        return 2


if __name__ == "__main__":
    sys.exit(main())
