"""Give each chunk of a mixed document its own categories, chosen by the model from that document's list.

Run from the repo root. Try a few chunks first and read the output:
    python scripts/taxonomy/label_chunks.py --limit 5
then the rest:
    python scripts/taxonomy/label_chunks.py

Results are saved to shared/taxonomy/chunk_overrides.json after every chunk. A chunk already in that file is
skipped, so the script can be stopped and run again without paying for the same chunk twice.
Only chunks of documents listed under `mixed:` in the taxonomy are labelled; every other chunk keeps its
document's categories.
"""
import argparse
import json
import os
import sys

from pydantic import BaseModel

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))   # the repo root, so `shared` is importable
from shared.taxonomy.taxonomy import HERE, load_taxonomy        # noqa: E402
from shared.taxonomy.chunk_ceator import NAMESPACES, all_chunks    # noqa: E402
from resolve import resolve                       # noqa: E402  (a sibling file: this folder is on sys.path when the script runs)

OVERRIDES_PATH = HERE / "chunk_overrides.json"

SYSTEM_PROMPT = (
    "You label a passage from a company document with policy categories.\n"
    "Answer with the numbers of every category the passage gives rules or facts for.\n"
    "Use only numbers from the list."
)


class ChunkLabels(BaseModel):
    numbers: list[int]


def build_prompt(domain: str, candidates: list[str], tax, text: str) -> str:
    lines = [f"{i}. {name}: {tax.categories[domain][name].description}" for i, name in enumerate(candidates)]
    return "Categories:\n" + "\n".join(lines) + "\n\nPassage:\n" + text


def label_chunks(index, llm, tax, overrides: dict, limit=None, save=None):
    done = failed = 0
    for ns in NAMESPACES:
        if not tax.mixed.get(ns):
            continue
        for chunk_id, meta in all_chunks(index, ns):
            source = str(meta.get("source", ""))
            if chunk_id in overrides or not tax.is_mixed(ns, source, chunk_id):
                continue
            if limit is not None and done + failed >= limit:
                return done, failed
            key = tax.document_key(ns, source, chunk_id)
            candidates = list(tax.documents[ns][key])
            text = str(meta.get("text", ""))
            try:
                answer = llm.invoke([("system", SYSTEM_PROMPT), ("human", build_prompt(ns, candidates, tax, text))])
                numbers = answer.numbers
            except Exception as e:
                failed += 1
                print(f"[{ns}] {chunk_id[:8]} FAILED ({type(e).__name__}: {e})")
                continue
            labels = resolve(numbers, candidates)
            overrides[chunk_id] = {"domain": ns, "document": key, "categories": labels}
            done += 1
            print(f"[{ns}] {chunk_id[:8]} model said {numbers} -> {labels} | {' '.join(text.split())[:50]}")
            if save:
                save(overrides)
    return done, failed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="label at most this many chunks, then stop")
    args = ap.parse_args()

    from pinecone import Pinecone
    from langchain.chat_models import init_chat_model
    index = Pinecone(api_key=os.environ["PINECONE_API_KEY"]).Index(os.environ["PINECONE_INDEX_NAME"])
    llm = (init_chat_model("groq:openai/gpt-oss-120b", temperature=0, reasoning_effort="low")
           .with_structured_output(ChunkLabels, method="json_schema", strict=True)
           .with_retry(stop_after_attempt=3))

    tax = load_taxonomy()
    overrides = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8")) if OVERRIDES_PATH.exists() else {}

    def save(data):
        OVERRIDES_PATH.write_text(json.dumps(data, indent=1, sort_keys=True), encoding="utf-8")

    done, failed = label_chunks(index, llm, tax, overrides, args.limit, save)
    print(f"labelled {done}, failed {failed}; {len(overrides)} chunks in {OVERRIDES_PATH.name}")


if __name__ == "__main__":
    main()