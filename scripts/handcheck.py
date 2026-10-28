"""Hand-check of the chunk labels: write a sample sheet, fill it in by eye, then score it.

    python scripts/handcheck.py --sample 30        # writes handcheck_sheet.csv (30 chunks drawn from all domains together)
    python scripts/handcheck.py --stratify         # 10 chunks per domain instead, so a small domain (hr) gets enough rows
    python scripts/handcheck.py --stratify 15      # 15 per domain
    (open the CSV in Excel, read each passage, type y or n in the "ok" column, save)
    python scripts/handcheck.py --score handcheck_sheet.csv

"ok" = y when every assigned category is really covered by the passage AND no category that the passage
clearly covers is missing. Anything else is n; say why in "note".
The sample is drawn with a fixed seed, so the same labels always give the same sample.
"""
import argparse
import csv
import json
import os
import random
import sys
from collections import defaultdict
from dotenv import load_dotenv
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))   # the repo root, so `shared` is importable
from shared.taxonomy.taxonomy import HERE            
load_dotenv()

OVERRIDES_PATH = HERE / "chunk_overrides.json"


def pick_sample(overrides: dict, n: int, seed: int = 7) -> list[str]:
    return random.Random(seed).sample(sorted(overrides), min(n, len(overrides)))


def pick_stratified(overrides: dict, per_domain: int = 10, seed: int = 7) -> list[str]:
    """`per_domain` chunk ids from each domain (all of them if a domain has fewer), in domain order.
    Same seed and same labels give the same sample."""
    by_domain = defaultdict(list)
    for cid in sorted(overrides):
        by_domain[overrides[cid]["domain"]].append(cid)
    rng = random.Random(seed)
    ids = []
    for domain in sorted(by_domain):
        ids.extend(rng.sample(by_domain[domain], min(per_domain, len(by_domain[domain]))))
    return ids


def write_sheet(index, overrides: dict, ids: list[str], path: str) -> None:
    by_domain = defaultdict(list)
    for cid in ids:
        by_domain[overrides[cid]["domain"]].append(cid)
    text = {}
    for domain, chunk_ids in by_domain.items():
        for start in range(0, len(chunk_ids), 100):
            batch = chunk_ids[start:start + 100]
            for cid, vec in index.fetch(ids=batch, namespace=domain).vectors.items():
                text[cid] = " ".join(str((vec.metadata or {}).get("text", "")).split())
    with open(path, "w", newline="", encoding="utf-8-sig") as f:      # utf-8-sig so Excel shows ₹ and arrows
        w = csv.writer(f)
        w.writerow(["chunk_id", "domain", "assigned", "ok (y/n)", "note", "text"])
        for cid in ids:
            e = overrides[cid]
            w.writerow([cid, e["domain"], "; ".join(e["categories"]), "", "", text.get(cid, "(not found)")[:700]])


def score(path: str) -> dict:
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    marks = [r["ok (y/n)"].strip().lower() for r in rows]
    answered = [m for m in marks if m in ("y", "n")]
    wrong = [r for r, m in zip(rows, marks) if m == "n"]
    return {"rows": len(rows), "answered": len(answered), "correct": answered.count("y"),
            "accuracy": round(answered.count("y") / len(answered), 3) if answered else None, "wrong": wrong}


def build_parser():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, help="N chunks drawn from all domains together (default 30)")
    ap.add_argument("--stratify", type=int, nargs="?", const=10, metavar="N",
                    help="N chunks per domain (default 10) instead of one sample over all domains")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--score")
    ap.add_argument("--out", default="handcheck_sheet.csv")
    return ap


def main():
    args = build_parser().parse_args()
    if args.score:
        s = score(args.score)
        print(f"{s['correct']} of {s['answered']} correct = {s['accuracy']}  ({s['rows'] - s['answered']} rows not filled in)")
        for r in s["wrong"]:
            print(" wrong:", r["chunk_id"][:12], "|", r["assigned"], "|", r["note"])
        return
    from pinecone import Pinecone
    index = Pinecone(api_key=os.environ["PINECONE_API_KEY"]).Index(os.environ["PINECONE_INDEX_NAME"])
    overrides = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))
    if args.stratify is not None:
        ids = pick_stratified(overrides, args.stratify, args.seed)
    else:
        ids = pick_sample(overrides, args.sample or 30, args.seed)
    write_sheet(index, overrides, ids, args.out)
    print(f"wrote {len(ids)} chunks to {args.out}")


if __name__ == "__main__":
    main()