"""Backfill: put the taxonomy's labels onto the chunks that are already stored.

Why this exists: the taxonomy knows which categories every chunk belongs to, but the stored chunks do not
carry that knowledge yet - it lives only in policy_taxonomy.yaml. A search cannot
filter on something the chunk does not carry. This script copies the labels onto each chunk, in Pinecone
(metadata, no re-embedding) and in the BM25 keyword indexes kept in Neon.

Fields written (see shared/taxonomy/tagging.py): categories, is_content, title (and original_title, the title
the chunk had before).

Run from the repo root:
    uv run python scripts/backfill.py                  DRY RUN: shows what would change, writes nothing
    uv run python scripts/backfill.py --apply          writes to Pinecone, then to the BM25 indexes
    uv run python scripts/backfill.py --namespace hr   only one domain
    uv run python scripts/backfill.py --report-orphans lists BM25 chunks with no Pinecone twin and the reverse (read-only)

Safe to run again: a chunk that is already correct is skipped. Only the five taxonomy domains are touched;
any other namespace in the index is listed and left alone.
"""
import argparse
import asyncio
import os
import pickle
import sys
from collections import Counter
from datetime import datetime, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from dotenv import load_dotenv                                                   # noqa: E402

from shared.taxonomy.taxonomy import load_taxonomy, DOMAINS, UNCATEGORIZED       # noqa: E402
from shared.taxonomy.tagging import tag_fields, fields_to_set                    # noqa: E402
from shared.taxonomy.chunk_ceator import all_chunks                              # noqa: E402


# ---------------------------------------------------------------- Pinecone

def plan_pinecone(index, tax, namespaces):
    """Look at every stored chunk and work out what has to be written. Writes nothing.

    Returns (updates, targets, stats):
      updates  list of (namespace, chunk_id, fields to set)
      targets  (namespace, source, text) -> what that chunk should carry; the BM25 step needs this
      stats    per namespace counts for the report
    """
    updates = []
    targets = {}
    stats = {}
    for ns in namespaces:
        count = Counter()
        uncategorized_sources = Counter()
        for chunk_id, meta in all_chunks(index, ns):
            source = str(meta.get("source", ""))
            target = tag_fields(tax, ns, source, meta.get("file_name"))
            changes = fields_to_set(target, meta)

            count["chunks"] += 1
            if target["categories"] == [UNCATEGORIZED]:
                count["uncategorized"] += 1
                uncategorized_sources[source] += 1
            if not target["is_content"]:
                count["non_content"] += 1
            if "original_title" in changes:
                count["original_title_saved"] += 1
            if changes:
                count["to_update"] += 1
                updates.append((ns, chunk_id, changes))
            else:
                count["already_correct"] += 1

            key = (ns, source, str(meta.get("text", "")))
            if key in targets and targets[key]["categories"] != target["categories"]:
                count["same_text_two_labels"] += 1     # the first label is the one used for the BM25 chunk
            targets.setdefault(key, target)
        stats[ns] = dict(count)
        stats[ns]["uncategorized_sources"] = dict(uncategorized_sources)
    return updates, targets, stats


def apply_pinecone(index, updates, log=print):
    """Write the planned fields. One failed chunk does not stop the rest. Returns (done, failed)."""
    done = 0
    failed = 0
    for ns, chunk_id, fields in updates:
        try:
            index.update(id=chunk_id, set_metadata=fields, namespace=ns)
            done += 1
        except Exception as e:
            failed += 1
            log(f"  FAILED [{ns}] {chunk_id[:8]}: {type(e).__name__}: {e}")
        if (done + failed) % 100 == 0:
            log(f"  ... {done + failed} of {len(updates)} chunks written")
    return done, failed


def skipped_namespaces(index, domains):
    """Namespaces in the index that the taxonomy does not cover, as (name, vector count)."""
    summary = index.describe_index_stats().namespaces
    return sorted((name, info.vector_count) for name, info in summary.items() if name not in domains)


# ---------------------------------------------------------------- BM25

def plan_bm25(chunks, namespace, tax, targets):
    """Labels for the chunks of one BM25 index. Returns (new list of chunks, stats). Saves nothing.

    A BM25 chunk has no chunk id, only text and source, so it is matched to its Pinecone twin by
    (source, text). A chunk with no twin only gets what its document gives.
    """
    new_chunks = []
    count = Counter()
    for chunk in chunks:
        count["chunks"] += 1
        if not isinstance(chunk, dict):
            count["plain_string_left_alone"] += 1       # nothing to attach labels to
            new_chunks.append(chunk)
            continue

        source = str(chunk.get("source", ""))
        target = targets.get((namespace, source, str(chunk.get("text", ""))))
        if target is None:
            target = tag_fields(tax, namespace, source, chunk.get("file_name"))
            count["no_pinecone_twin"] += 1
            if target["categories"] == [UNCATEGORIZED]:
                count["no_twin_uncategorized"] += 1

        wanted = {"categories": target["categories"], "is_content": target["is_content"]}
        if "title" in target:
            wanted["title"] = target["title"]

        if any(chunk.get(key) != value for key, value in wanted.items()):
            new_chunks.append({**chunk, **wanted})
            count["to_update"] += 1
        else:
            new_chunks.append(chunk)
            count["already_correct"] += 1
    return new_chunks, dict(count)


async def load_bm25(conn, namespace):
    row = await conn.fetchrow('SELECT "indexData" FROM bm25_indexes WHERE namespace=$1', namespace)
    return pickle.loads(row["indexData"]) if row else None


async def save_bm25(conn, namespace, data):
    await conn.execute(
        'UPDATE bm25_indexes SET "indexData"=$2, "updatedAt"=$3 WHERE namespace=$1',
        namespace, pickle.dumps(data), datetime.now(timezone.utc).replace(tzinfo=None),
    )


async def run_bm25(conn, tax, targets, namespaces, apply):
    """Plan (and with apply=True, save) the labels of every namespace's BM25 index. Returns stats per namespace."""
    results = {}
    for ns in namespaces:
        data = await load_bm25(conn, ns)
        if data is None:
            results[ns] = {"no_index": True}
            continue
        new_chunks, stats = plan_bm25(data["chunks"], ns, tax, targets)
        if apply and stats.get("to_update"):
            data["chunks"] = new_chunks      # BM25 scores only use the text, so the index object itself stays as it is
            await save_bm25(conn, ns, data)
        results[ns] = stats
    return results


# ---------------------------------------------------------------- report

def print_report(pine_stats, bm25_stats, skipped, apply, log=print):
    log("")
    log("PINECONE")
    for ns, s in pine_stats.items():
        log(f"  {ns:12s} chunks {s.get('chunks', 0):4d} | already correct {s.get('already_correct', 0):4d} | "
            f"to update {s.get('to_update', 0):4d} | non_content {s.get('non_content', 0):3d} | "
            f"uncategorized {s.get('uncategorized', 0):3d} | old title saved {s.get('original_title_saved', 0):3d}")
        for source, n in s.get("uncategorized_sources", {}).items():
            log(f"      uncategorized: {source[-70:]} ({n} chunks)")
        if s.get("same_text_two_labels"):
            log(f"      note: {s['same_text_two_labels']} chunks have the same text as an earlier chunk but a different label")
    log("")
    log("BM25 KEYWORD INDEXES")
    for ns, s in bm25_stats.items():
        if s.get("no_index"):
            log(f"  {ns:12s} no keyword index stored")
            continue
        log(f"  {ns:12s} chunks {s.get('chunks', 0):4d} | already correct {s.get('already_correct', 0):4d} | "
            f"to update {s.get('to_update', 0):4d} | no Pinecone twin {s.get('no_pinecone_twin', 0):3d} "
            f"(uncategorized {s.get('no_twin_uncategorized', 0)}) | plain strings {s.get('plain_string_left_alone', 0)}")
    if skipped:
        log("")
        log("Namespaces in the index that the taxonomy does not cover (left alone): "
            + ", ".join(f"{name} ({n} vectors)" for name, n in skipped))
    log("")
    if not apply:
        log("DRY RUN - nothing was written. Run again with --apply to write these changes.")


# ---------------------------------------------------------------- orphans (report mode)

def snippet(text, width=70):
    return " ".join(str(text).split())[:width]


def find_orphans(pinecone_items, bm25_chunks, namespace, tax):
    """Compare the two stores of one namespace. Reads only.

    pinecone_items  iterable of (chunk_id, metadata)
    bm25_chunks     the "chunks" list of that namespace's BM25 pickle

    A BM25 chunk has no chunk id, so it is identified by its position in the pickle, and matched to Pinecone by
    (source, text) like the backfill does. A plain-string BM25 chunk has no source, so it is matched by text alone.

    Returns (bm25_only, pinecone_only):
      bm25_only      [{"position", "source", "doc_id", "categories", "text"}] chunks Pinecone does not have
      pinecone_only  [{"chunk_id", "source", "text"}] chunks the BM25 index does not have
    """
    pine = list(pinecone_items)
    pine_keys = {(str(m.get("source", "")), str(m.get("text", ""))) for _, m in pine}
    pine_texts = {str(m.get("text", "")) for _, m in pine}

    bm25_keys, bm25_texts, bm25_only = set(), set(), []
    for position, chunk in enumerate(bm25_chunks):
        if isinstance(chunk, dict):
            source, text = str(chunk.get("source", "")), str(chunk.get("text", ""))
            bm25_keys.add((source, text))
            bm25_texts.add(text)
            if (source, text) not in pine_keys:
                categories = tag_fields(tax, namespace, source, chunk.get("file_name"))["categories"]
                bm25_only.append({"position": position, "source": source, "doc_id": chunk.get("doc_id"),
                                  "categories": categories, "text": snippet(text)})
        else:
            bm25_texts.add(str(chunk))
            if str(chunk) not in pine_texts:
                bm25_only.append({"position": position, "source": "(plain string)", "doc_id": None,
                                  "categories": [UNCATEGORIZED], "text": snippet(chunk)})

    pinecone_only = [{"chunk_id": chunk_id, "source": str(m.get("source", "")), "text": snippet(m.get("text", ""))}
                     for chunk_id, m in pine
                     if (str(m.get("source", "")), str(m.get("text", ""))) not in bm25_keys
                     and str(m.get("text", "")) not in bm25_texts]
    return bm25_only, pinecone_only


def print_orphans(results, log=print):
    """results: {namespace: (bm25_only, pinecone_only) or None when the namespace has no BM25 index}"""
    for ns, found in results.items():
        log("")
        if found is None:
            log(f"{ns}: no keyword index stored, so nothing to compare")
            continue
        bm25_only, pinecone_only = found
        log(f"{ns}: {len(bm25_only)} keyword-index chunks are not in Pinecone, "
            f"{len(pinecone_only)} Pinecone chunks are not in the keyword index")
        for o in bm25_only:
            log(f"  BM25 only  #{o['position']:<4d} {o['source'][-50:]:50s} doc_id={o['doc_id']} "
                f"would be {o['categories']} | {o['text']}")
        for o in pinecone_only:
            log(f"  Pinecone only  {o['chunk_id']} {o['source'][-50:]:50s} | {o['text']}")
    log("")
    log("Nothing was changed. A keyword-only chunk is a stale entry (its document was deleted or re-ingested from Pinecone "
        "only): re-ingest that document or delete it with the ingestion service's delete-document call, "
        "which removes it from both stores. A Pinecone-only chunk is missing from keyword search until its document is "
        "re-ingested.")


# ---------------------------------------------------------------- main

def build_parser():
    ap = argparse.ArgumentParser(description="Put the taxonomy's labels onto stored chunks (dry run unless --apply).")
    ap.add_argument("--apply", action="store_true", help="write the changes (the default is a dry run)")
    ap.add_argument("--namespace", choices=DOMAINS, help="only this domain")
    ap.add_argument("--report-orphans", action="store_true",
                    help="read-only: list BM25 chunks missing from Pinecone and Pinecone chunks missing from BM25")
    return ap


async def run_orphans(index, conn, tax, namespaces):
    results = {}
    for ns in namespaces:
        data = await load_bm25(conn, ns)
        results[ns] = None if data is None else find_orphans(all_chunks(index, ns), data["chunks"], ns, tax)
    return results


def execute(args, tax, index, connect, log=print):
    """Run what `args` asks for. `connect` is an async function returning a database connection.
    Returns the number of Pinecone chunks that failed to write."""
    namespaces = [args.namespace] if args.namespace else list(DOMAINS)

    if args.report_orphans:
        if args.apply:
            raise SystemExit("--report-orphans only reads; do not combine it with --apply.")

        async def orphan_step():
            conn = await connect()
            try:
                return await run_orphans(index, conn, tax, namespaces)
            finally:
                await conn.close()

        print_orphans(asyncio.run(orphan_step()), log)
        return 0

    log(f"{'APPLYING' if args.apply else 'DRY RUN'}: reading the chunks of {', '.join(namespaces)} ...")
    updates, targets, pine_stats = plan_pinecone(index, tax, namespaces)

    failed = 0
    if args.apply:
        done, failed = apply_pinecone(index, updates, log)
        log(f"Pinecone: {done} chunks updated, {failed} failed")

    async def bm25_step():
        conn = await connect()
        try:
            return await run_bm25(conn, tax, targets, namespaces, args.apply)
        finally:
            await conn.close()

    bm25_stats = asyncio.run(bm25_step())
    print_report(pine_stats, bm25_stats, skipped_namespaces(index, DOMAINS), args.apply, log)
    return failed


def main():
    args = build_parser().parse_args()

    load_dotenv()
    load_dotenv(os.path.join(ROOT, "services", "ingestion_service", ".env"))     # DATABASE_URL is kept there
    if not os.environ.get("DATABASE_URL"):
        sys.exit("DATABASE_URL is not set, so the BM25 indexes cannot be read.")

    from pinecone import Pinecone
    import asyncpg

    index = Pinecone(api_key=os.environ["PINECONE_API_KEY"]).Index(os.environ["PINECONE_INDEX_NAME"])

    async def connect():
        return await asyncpg.connect(os.environ["DATABASE_URL"])

    if execute(args, load_taxonomy(), index, connect):
        sys.exit(1)


if __name__ == "__main__":
    main()
