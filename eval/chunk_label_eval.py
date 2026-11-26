"""How often does chunk-level labelling keep the right category? A human-labelled sample against the real labeller.

The search filter is $in, so the harmful mistake is a MISSING correct label (the chunk drops out of the filter). The
main number is therefore the gold-hit rate: every gold label is among the labels the model chose. An extra label only
costs some precision, which the labels-per-chunk averages show.

  export   picks chunks whose document has 2+ categories and writes them with an EMPTY "gold" list. Fill "gold" by
           hand from each chunk's "candidates", without looking at the stored or the model's labels.
  score    labels the same chunks with the ingestion's prompt and model and compares them with "gold". Rows whose
           "gold" is still empty are skipped.

A failed model call makes the labeller keep the whole candidate list, which always counts as a hit, so `score` also
reports how many answers fell back.

  uv run python eval/chunk_label_eval.py export --namespace hr --n 80 --seed 7 --out eval/chunk_gold.json
  uv run python eval/chunk_label_eval.py score --gold eval/chunk_gold.json --repeat 2
"""
import argparse
import json
import math
import os
import random
import sys
from collections import Counter
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from shared.taxonomy.chunk_ceator import all_chunks                                      # noqa: E402  (also loads .env)
from shared.taxonomy.chunk_labeler import build_openai_labeler, label_chunks, only_candidates  # noqa: E402
from shared.taxonomy.taxonomy import DOMAINS, load_taxonomy                              # noqa: E402

RESULTS_DIR = os.path.join(HERE, "results")
Z_95 = 1.959964
MISSES_SHOWN = 10


def sample_chunks(index, taxonomy, namespace: str, n: int, seed: int) -> list[dict]:
    """At most ceil(n / documents) chunks of each document, so one large document does not dominate. The stored
    labels are deliberately not copied: the person filling in "gold" must not see them."""
    documents: dict[str, list[dict]] = {}
    for chunk_id, meta in all_chunks(index, namespace):
        source, file_name = str(meta.get("source", "")), meta.get("file_name")
        candidates = taxonomy.for_chunk(namespace, source, file_name)
        text = str(meta.get("text") or "").strip()
        if len(candidates) < 2 or not text:
            continue
        doc = taxonomy.document_key(namespace, source, file_name)
        documents.setdefault(doc, []).append({"id": chunk_id, "domain": namespace, "doc": doc,
                                              "candidates": list(candidates), "text": text, "gold": []})
    if not documents:
        return []
    cap, chooser, sample = math.ceil(n / len(documents)), random.Random(seed), []
    for doc in sorted(documents):                       # sorted, so the index's listing order cannot change the sample
        rows = sorted(documents[doc], key=lambda row: row["id"])
        sample.extend(chooser.sample(rows, min(cap, len(rows))))
    return sample


def check_gold(rows: list[dict]) -> None:
    """A typo in a gold label must stop the run, or it would be counted as a model miss."""
    problems = []
    for row in rows:
        gold = row.get("gold") or []
        if not isinstance(gold, list):
            problems.append(f"{row['id']}: gold must be a list")
            continue
        unknown = [name for name in gold if name not in row["candidates"]]
        if unknown:
            problems.append(f"{row['id']}: gold {unknown} not in the candidates {row['candidates']}")
    problems += [f"{key}: the id appears {count} times" for key, count in Counter(r["id"] for r in rows).items() if count > 1]
    if problems:
        raise ValueError("gold file is invalid:\n  " + "\n  ".join(problems))


def wilson(successes: int, n: int, z: float = Z_95) -> tuple[float, float] | None:
    """95% interval for a share; unlike the normal approximation it stays inside 0..1 for small samples."""
    if not n:
        return None
    share = successes / n
    scale = 1 + z * z / n
    centre = (share + z * z / (2 * n)) / scale
    half = z * math.sqrt(share * (1 - share) / n + z * z / (4 * n * n)) / scale
    return max(0.0, centre - half), min(1.0, centre + half)


def score(rows: list[dict], predictions: dict[str, list[str]]) -> dict:
    """The metrics for the rows that have gold labels. `predictions` is {chunk id: labels the model chose}."""
    check_gold(rows)
    judged = [row for row in rows if row.get("gold")]
    chunks = []
    for row in judged:
        gold, got = set(row["gold"]), set(predictions[row["id"]])
        chunks.append({"id": row["id"], "domain": row["domain"], "doc": row.get("doc"), "candidates": row["candidates"],
                       "gold": row["gold"], "got": predictions[row["id"]], "hit": gold <= got,
                       "overlap": bool(gold & got), "exact": gold == got, "full_list": got == set(row["candidates"])})
    n = len(chunks)
    hits = sum(c["hit"] for c in chunks)

    def mean(key: str) -> float | None:
        return sum(len(c[key]) for c in chunks) / n if n else None

    def share(key: str) -> float | None:
        return sum(c[key] for c in chunks) / n if n else None

    missed = Counter(name for c in chunks for name in c["gold"] if name not in c["got"])
    return {"n": n, "skipped": len(rows) - n, "hits": hits, "hit_rate": share("hit"), "hit_interval": wilson(hits, n),
            "overlap_rate": share("overlap"), "exact_rate": share("exact"),
            "labels_model": mean("got"), "labels_gold": mean("gold"), "labels_baseline": mean("candidates"),
            "full_list": sum(c["full_list"] for c in chunks),
            "most_missed": sorted(missed.items(), key=lambda item: (-item[1], item[0])),
            "misses": [(c["id"], c["gold"], c["got"]) for c in chunks if not c["hit"]], "chunks": chunks}


class CountingLabeler:
    """Passes the batch to the real model and counts the answers label_chunks will replace by the whole list."""

    def __init__(self, llm):
        self.llm, self.candidates, self.fell_back = llm, [], 0

    def batch(self, messages, **kwargs):
        try:
            answers = self.llm.batch(messages, **kwargs)
        except Exception:
            self.fell_back += len(messages)
            raise
        self.fell_back += sum(isinstance(a, Exception) or not only_candidates(a, self.candidates) for a in answers)
        return answers


def predict(llm, taxonomy, rows: list[dict]) -> tuple[dict[str, list[str]], int]:
    """({chunk id: labels}, number of fallbacks). One batch per (domain, candidates) group, as ingestion does."""
    groups: dict[tuple, list[dict]] = {}
    for row in rows:
        groups.setdefault((row["domain"], tuple(row["candidates"])), []).append(row)
    counting, predictions = CountingLabeler(llm), {}
    for (domain, candidates), items in groups.items():
        counting.candidates = list(candidates)
        labels = label_chunks(counting, taxonomy, domain, candidates, [row["text"] for row in items])
        predictions.update({row["id"]: chosen for row, chosen in zip(items, labels)})
    return predictions, counting.fell_back


def changed_share(first: dict, second: dict) -> float | None:
    return sum(set(first[key]) != set(second[key]) for key in first) / len(first) if first else None


def report(result: dict) -> str:
    if not result["n"]:
        return f"No row has gold labels yet ({result['skipped']} skipped)."
    low, high = result["hit_interval"]
    lines = [f"model {result['model']}",
             f"chunks scored {result['n']} | skipped (empty gold) {result['skipped']}",
             f"gold-hit rate    {result['hit_rate']:.1%}  (95% Wilson {low:.1%} to {high:.1%})",
             f"any-overlap rate {result['overlap_rate']:.1%}",
             f"exact-match rate {result['exact_rate']:.1%}",
             f"labels per chunk: model {result['labels_model']:.2f} | gold {result['labels_gold']:.2f} | "
             f"baseline (whole document list) {result['labels_baseline']:.2f}",
             f"results equal to the full candidate list: {result['full_list']}"]
    for number, fell_back in enumerate(result["fell_back"], start=1):
        lines.append(f"run {number}: answers that failed or were unusable (kept the full list): {fell_back}")
    if "changed_between_runs" in result:
        lines.append(f"chunks whose labels differ between the two runs: {result['changed_between_runs']:.1%}")
    if result["misses"]:
        lines.append("most-missed gold categories: " + ", ".join(f"{name} ({count})" for name, count in result["most_missed"][:10]))
        lines.append(f"first {min(MISSES_SHOWN, len(result['misses']))} of {len(result['misses'])} misses (id, gold, got):")
        lines += [f"  {miss}" for miss in result["misses"][:MISSES_SHOWN]]
    return "\n".join(lines)


def run_score(rows: list[dict], llm, taxonomy, repeat: int) -> dict:
    check_gold(rows)                                    # before any call, so a typo costs nothing
    judged = [row for row in rows if row.get("gold")]
    runs = [predict(llm, taxonomy, judged) for _ in range(repeat if judged else 0)]
    result = score(rows, runs[0][0] if runs else {})
    result["fell_back"] = [fell_back for _, fell_back in runs]
    if len(runs) == 2:
        result["changed_between_runs"] = changed_share(runs[0][0], runs[1][0])
        for chunk in result["chunks"]:
            chunk["got_second_run"] = runs[1][0][chunk["id"]]
    return result


def save_result(result: dict) -> str:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    path = os.path.join(RESULTS_DIR, f"chunk_label_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json")
    with open(path, "w", encoding="utf-8") as file:
        json.dump(result, file, indent=1)
    return path


def export_command(args) -> int:
    if os.path.exists(args.out):
        print(f"{args.out} already exists and may hold hand-filled gold labels; choose another --out or delete it")
        return 2
    from pinecone import Pinecone
    index = Pinecone(api_key=os.environ["PINECONE_API_KEY"]).Index(os.environ["PINECONE_INDEX_NAME"])
    rows = sample_chunks(index, load_taxonomy(), args.namespace, args.n, args.seed)
    if not rows:
        print(f"no chunk in '{args.namespace}' has two or more candidate categories; nothing written")
        return 2
    with open(args.out, "w", encoding="utf-8") as file:
        json.dump(rows, file, indent=1, ensure_ascii=False)
    print(f"wrote {len(rows)} chunks from {len({r['doc'] for r in rows})} documents to {args.out}; fill in each 'gold' list")
    return 0


def score_command(args) -> int:
    with open(args.gold, encoding="utf-8") as file:
        rows = json.load(file)
    try:
        check_gold(rows)
    except ValueError as error:
        print(error)
        return 2
    if not any(row.get("gold") for row in rows):
        print(f"No row has gold labels yet ({len(rows)} skipped).")
        return 2
    if not os.getenv("OPENAI_API_KEY"):
        print("score needs OPENAI_API_KEY")
        return 2
    model = os.getenv("LABELING_MODEL", "gpt-4o-mini")
    llm = build_openai_labeler(model, os.environ["OPENAI_API_KEY"])
    result = {"model": model, **run_score(rows, llm, load_taxonomy(), args.repeat)}
    print(report(result))
    print("stored", save_result(result))
    if any(fell_back == result["n"] for fell_back in result["fell_back"]):
        print("EVERY answer of a run fell back to the full list: these numbers do not measure the model")
        return 1
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate chunk-level labelling.")
    commands = parser.add_subparsers(dest="command", required=True)
    export = commands.add_parser("export", help="write a sample of chunks to label by hand")
    export.add_argument("--namespace", required=True, choices=list(DOMAINS))
    export.add_argument("--n", type=int, default=80)
    export.add_argument("--seed", type=int, default=7)
    export.add_argument("--out", default=os.path.join(HERE, "chunk_gold.json"))
    export.set_defaults(run=export_command)
    scoring = commands.add_parser("score", help="compare the model's labels with the hand-filled gold labels")
    scoring.add_argument("--gold", required=True)
    scoring.add_argument("--repeat", type=int, choices=[1, 2], default=1)
    scoring.set_defaults(run=score_command)
    args = parser.parse_args(argv)
    return args.run(args)


if __name__ == "__main__":
    sys.exit(main())
