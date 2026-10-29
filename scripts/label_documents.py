"""Label every stored chunk with its document's categories (Pinecone metadata only, no re-embedding).

The search filter can only use labels a chunk already carries; a chunk is labelled by looking its document up in
shared/taxonomy/policy_taxonomy.yaml, so run this after editing that file.
    uv run python scripts/label_documents.py [--apply] [--namespace hr]     (the default is a DRY RUN)
A second --apply changes nothing. A namespace not in the taxonomy is skipped with a warning. The keyword (BM25)
indexes are NOT touched by this script.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from shared.taxonomy.chunk_ceator import all_chunks              # noqa: E402  (also loads .env)
from shared.taxonomy.tagging import fields_to_set, tag_fields    # noqa: E402
from shared.taxonomy.taxonomy import DOMAINS, load_taxonomy      # noqa: E402


def label_namespace(index, taxonomy, namespace: str, apply: bool, log=print) -> dict:
    """One namespace at a time, so the dry run shows per-domain counts and one failed chunk cannot stop the others."""
    counts = {"chunks": 0, "to_change": 0, "failed": 0}
    for chunk_id, meta in all_chunks(index, namespace):
        counts["chunks"] += 1
        wanted = tag_fields(taxonomy, namespace, str(meta.get("source", "")), meta.get("file_name"))
        changes = fields_to_set(wanted, meta)
        if not changes:
            continue
        counts["to_change"] += 1
        if apply:
            try:
                index.update(id=chunk_id, set_metadata=changes, namespace=namespace)
            except Exception as error:
                counts["failed"] += 1
                log(f"  FAILED [{namespace}] {chunk_id[:8]}: {type(error).__name__}: {error}")
    return counts


def run(index, taxonomy, only_namespace, apply: bool, log=print) -> int:
    """Labels the chosen namespaces and returns how many writes failed, which is the exit status."""
    log("APPLYING" if apply else "DRY RUN: nothing is written")
    failed = 0
    for namespace in [only_namespace] if only_namespace else list(DOMAINS):
        if namespace not in DOMAINS:
            log(f"WARNING: '{namespace}' is not in the taxonomy; skipped")
            continue
        counts = label_namespace(index, taxonomy, namespace, apply, log)
        log(f"{namespace:12s} chunks {counts['chunks']:5d} | to change {counts['to_change']:5d} | failed {counts['failed']}")
        failed += counts["failed"]
    for name in index.describe_index_stats().namespaces:
        if name not in DOMAINS:
            log(f"WARNING: namespace '{name}' in the index is not in the taxonomy; left alone")
    return failed


def main():
    parser = argparse.ArgumentParser(description="Label stored chunks with their document's categories.")
    parser.add_argument("--apply", action="store_true", help="write the labels (the default is a dry run)")
    parser.add_argument("--namespace", help="only this domain")
    args = parser.parse_args()

    from pinecone import Pinecone
    index = Pinecone(api_key=os.environ["PINECONE_API_KEY"]).Index(os.environ["PINECONE_INDEX_NAME"])
    if run(index, load_taxonomy(), args.namespace, args.apply):
        sys.exit(1)


if __name__ == "__main__":
    main()
