"""Label every stored chunk with its categories (Pinecone metadata only, no re-embedding).

The search filter can only use labels a chunk already carries. By default a chunk is labelled by looking its document up
in shared/taxonomy/policy_taxonomy.yaml, so run this after editing that file.
    uv run python scripts/label_documents.py [--apply] [--namespace hr]     (the default is a DRY RUN)
A second --apply changes nothing. A namespace not in the taxonomy is skipped with a warning.

Two options for chunk-level labels (see shared/taxonomy/chunk_labeler.py):
    --chunk-level     a language model chooses each chunk's categories from its document's list, instead of every chunk
                      getting the whole list. Needs OPENAI_API_KEY. A dry run still calls the model (to show what it
                      would choose) but writes nothing. Without this flag the labels go back to the document's list.
    --keyword-index   also copy the labels to the keyword (BM25) index in Postgres, so the vector search and the keyword
                      search filter on the same labels. Needs DATABASE_URL. The index is matched to Pinecone by
                      (doc_id, text); a keyword chunk with no match is left alone and counted.
"""
import argparse
import os
import pickle
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from shared.taxonomy.chunk_ceator import all_chunks              # noqa: E402  (also loads .env)
from shared.taxonomy.chunk_labeler import label_chunks           # noqa: E402
from shared.taxonomy.tagging import fields_to_set, tag_fields    # noqa: E402
from shared.taxonomy.taxonomy import DOMAINS, load_taxonomy      # noqa: E402

SAMPLES_SHOWN = 6        # chunks whose chosen labels are printed, so a dry run can be judged by eye


def chunk_level_labels(taxonomy, namespace: str, chunks: list, labeler) -> dict[str, list[str]]:
    """{chunk_id: categories the model chose}. Chunks of the same document are sent together, one batch per document.
    A chunk with no text is left out, and then keeps its document's whole list."""
    groups: dict[tuple, list] = {}
    for chunk_id, meta in chunks:
        text = str(meta.get("text") or "").strip()
        if not text:
            continue
        candidates = tuple(taxonomy.for_chunk(namespace, str(meta.get("source", "")), meta.get("file_name")))
        groups.setdefault(candidates, []).append((chunk_id, text))
    chosen: dict[str, list[str]] = {}
    for candidates, items in groups.items():
        for (chunk_id, _), categories in zip(items, label_chunks(labeler, taxonomy, namespace, candidates,
                                                                 [text for _, text in items])):
            chosen[chunk_id] = categories
    return chosen


def label_namespace(index, taxonomy, namespace: str, apply: bool, log=print, labeler=None, collect=None, stats=None) -> dict:
    """One namespace at a time, so the dry run shows per-domain counts and one failed chunk cannot stop the others.

    `labeler` (optional) makes the labels chunk-level. `collect` (optional dict) receives {(doc_id, text): wanted fields}
    for every chunk, which is what the keyword index is matched against. `stats` (optional dict) receives the extra
    numbers for the report (categories per chunk before and after, a few example chunks); the returned counts keep
    their three keys, so existing callers are unaffected.
    """
    counts = {"chunks": 0, "to_change": 0, "failed": 0}
    stats = stats if stats is not None else {}
    stats.update({"categories_before": 0, "categories_after": 0, "samples": []})
    chunks = list(all_chunks(index, namespace))
    chosen = chunk_level_labels(taxonomy, namespace, chunks, labeler) if labeler is not None else {}
    for chunk_id, meta in chunks:
        counts["chunks"] += 1
        wanted = tag_fields(taxonomy, namespace, str(meta.get("source", "")), meta.get("file_name"), chosen.get(chunk_id))
        stats["categories_before"] += len(meta.get("categories") or [])
        stats["categories_after"] += len(wanted["categories"])
        if collect is not None:
            collect[(meta.get("doc_id"), meta.get("text"))] = wanted
        if chunk_id in chosen and len(stats["samples"]) < SAMPLES_SHOWN:
            stats["samples"].append((str(meta.get("text", ""))[:100].replace("\n", " "), wanted["categories"]))
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


def sync_keyword_index(conn, namespace: str, labels: dict, apply: bool) -> dict:
    """Copy the labels onto the keyword index of one namespace. `labels` is {(doc_id, text): wanted fields}.

    The index is one pickled object per namespace in Postgres (the same one ingestion writes). Changing a chunk's labels
    does not change its words, so the scoring part of the index is untouched and only the labels are rewritten.
    Only run this against your own database: unpickling runs code from the data, as the ingestion service already does.
    """
    with conn.cursor() as cur:
        cur.execute('SELECT "indexData" FROM bm25_indexes WHERE namespace = %s', (namespace,))
        row = cur.fetchone()
    result = {"chunks": 0, "to_change": 0, "unmatched": 0}
    if row is None:
        return result
    data = pickle.loads(row[0])
    for chunk in data["chunks"]:
        result["chunks"] += 1
        wanted = labels.get((chunk.get("doc_id"), chunk.get("text"))) if isinstance(chunk, dict) else None
        if wanted is None:
            result["unmatched"] += 1
            continue
        changes = fields_to_set(wanted, chunk)
        if changes:
            result["to_change"] += 1
            chunk.update(changes)
    if apply and result["to_change"]:
        with conn.transaction(), conn.cursor() as cur:
            cur.execute('UPDATE bm25_indexes SET "indexData" = %s, "updatedAt" = %s WHERE namespace = %s',
                        (pickle.dumps(data), datetime.now(timezone.utc).replace(tzinfo=None), namespace))
    return result


def run(index, taxonomy, only_namespace, apply: bool, log=print, labeler=None, conn=None) -> int:
    """Labels the chosen namespaces and returns how many writes failed, which is the exit status."""
    log("APPLYING" if apply else "DRY RUN: nothing is written")
    failed = 0
    for namespace in [only_namespace] if only_namespace else list(DOMAINS):
        if namespace not in DOMAINS:
            log(f"WARNING: '{namespace}' is not in the taxonomy; skipped")
            continue
        collect = {} if conn is not None else None
        stats = {}
        counts = label_namespace(index, taxonomy, namespace, apply, log, labeler, collect, stats)
        log(f"{namespace:12s} chunks {counts['chunks']:5d} | to change {counts['to_change']:5d} | failed {counts['failed']}")
        if labeler is not None and counts["chunks"]:
            log(f"{'':12s} categories per chunk: {stats['categories_before'] / counts['chunks']:.1f} now -> "
                f"{stats['categories_after'] / counts['chunks']:.1f} after")
            for text, categories in stats["samples"]:
                log(f"{'':14s}e.g. {categories} <- {text!r}")
        if conn is not None:
            kw = sync_keyword_index(conn, namespace, collect, apply)
            log(f"{'':12s} keyword index: chunks {kw['chunks']:4d} | to change {kw['to_change']:4d} | no match in Pinecone {kw['unmatched']}")
        failed += counts["failed"]
    for name in index.describe_index_stats().namespaces:
        if name not in DOMAINS:
            log(f"WARNING: namespace '{name}' in the index is not in the taxonomy; left alone")
    return failed


def main():
    parser = argparse.ArgumentParser(description="Label stored chunks with their categories.")
    parser.add_argument("--apply", action="store_true", help="write the labels (the default is a dry run)")
    parser.add_argument("--namespace", help="only this domain")
    parser.add_argument("--chunk-level", action="store_true", help="a model chooses each chunk's categories (needs OPENAI_API_KEY)")
    parser.add_argument("--keyword-index", action="store_true", help="also copy the labels to the keyword index (needs DATABASE_URL)")
    args = parser.parse_args()

    from pinecone import Pinecone
    index = Pinecone(api_key=os.environ["PINECONE_API_KEY"]).Index(os.environ["PINECONE_INDEX_NAME"])
    labeler = None
    if args.chunk_level:
        from shared.taxonomy.chunk_labeler import build_openai_labeler
        labeler = build_openai_labeler(os.getenv("LABELING_MODEL", "gpt-4o-mini"), os.environ["OPENAI_API_KEY"])
    if args.keyword_index:
        import psycopg
        # prepare_threshold=None: the Neon pooler can drop server-side prepared statements between calls
        with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=5, prepare_threshold=None) as conn:
            failed = run(index, load_taxonomy(), args.namespace, args.apply, labeler=labeler, conn=conn)
    else:
        failed = run(index, load_taxonomy(), args.namespace, args.apply, labeler=labeler)
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
