# Localization runbook (Windows PowerShell + uv)

The ordered commands that take the localization work from "tested with fakes" to "measured on the real services".
Run everything from the repository root unless a line says otherwise. Nothing here has been run against the live
services by the assistant that wrote it; the "expect" column says what a healthy run should look like, so a
difference is a signal to stop and look, not to carry on.

Credentials: `scripts/backfill.py` reads `PINECONE_API_KEY`, `PINECONE_INDEX_NAME` (root
`.env`) and `DATABASE_URL` (`services\ingestion_service\.env`). The paste-back lines say what to send me.

## 0. Once: rebuild the services that changed

```powershell
docker compose up -d --build --no-deps orchestrator retrieval-service ingestion-service api-gateway
```
Expect: four containers recreated, then healthy. If a build fails, paste the last 20 lines of the error. (The retrieval
service now skips the localized filter for a namespace outside the taxonomy, so it needs this rebuild too.)

## 1. Backfill: dry run (reads Pinecone and Neon, writes nothing)

```powershell
uv run python scripts/backfill.py
```
Expect: a `PINECONE` block and a `BM25 KEYWORD INDEXES` block per domain, ending with
`DRY RUN - nothing was written`. **First time:** `to update` is non-zero (the labels are not stored yet) and
`already correct` is the rest. **If `to update` is 0 everywhere**, the labels are already stored: skip step 2.
**If a known document is listed as `uncategorized:`**, its file name is missing from `policy_taxonomy.yaml`; fix
the yaml, not the data. Paste the whole output back.

```powershell
uv run python scripts/backfill.py --report-orphans
```
Expect: per domain, how many keyword-index chunks are not in Pinecone (the ~10 stale ones) and the reverse, each
listed with position, source and the categories it would get; `support: no keyword index stored`. It changes
nothing. A keyword-only chunk is stale: re-ingest or delete its document (the ingestion service's delete-document
call removes it from both stores). If the list is long or lists a whole document, tell me before deleting anything.

## 2. Backfill: apply (writes labels to Pinecone metadata and to the BM25 pickles in Neon)

Only after you have read the dry run and are happy with it.

```powershell
uv run python scripts/backfill.py --apply
```
Expect: `Pinecone: N chunks updated, 0 failed`, then the report without the DRY RUN line. If `failed` is not 0 the
command exits with status 1; run it again (it only retries what is still missing).

```powershell
uv run python scripts/backfill.py
```
Expect: `to update   0` for every domain in both blocks (safe to repeat). Anything else: paste the output.

## 3. Evaluation: all four levels

Write `eval\localize\questions.jsonl` yourself (copy `questions.example.jsonl`, replace the rows; both `tune` and
`heldout` rows are required or the runner refuses).

```powershell
uv run python eval/localize/runner.py run-all --dry-run --questions eval/localize/questions.jsonl
```
Expect: `DRY RUN: every number below comes from a FAKE client...`, four `stored` lines, a table, and
`wrote ...results_dryrun\comparison.csv/.md`. This only checks the format and your question file; ignore the numbers.
If it prints `question set is invalid`, fix the listed lines.

```powershell
$env:INTERNAL_SHARED_SECRET = "<same value as the orchestrator>"
$env:EVAL_EMPLOYEE_EMAIL    = "<an employee e-mail allowed to read all five domains>"
uv run python eval/localize/runner.py run-all --questions eval/localize/questions.jsonl --switch compose
```
Expect: for each of off, filter, prompt, full: the stack is restarted, then `stored ...results\<level>.json`; at the end
the table and `wrote ...results\comparison.csv` / `comparison.md`. **If a `WARNING: N of M questions FAILED` appears**,
those questions are in the "requests that failed" row and not in the rates: look at the named errors (timeout = a
slow service, HTTP 401/403 = wrong secret or email). **If a `WARNING: ... NOT running with LOCALIZE=...` appears**,
that level did not take effect: stop and tell me. Use `--switch manual` if you prefer to set `LOCALIZE` yourself.

```powershell
uv run python eval/localize/runner.py report --questions eval/localize/questions.jsonl
```
Expect: the same table rebuilt from the stored files (use it after fixing one level by running `run --level <x>` again).

## 4. The test suites (any time)

```powershell
cd shared;                       uv run python -m pytest taxonomy/tests ; cd ..
uv run python -m pytest scripts/tests
uv run python -m pytest eval/localize/tests
cd services\orchestrator;        uv run python -m pytest tests ; cd ..\..
cd services\retrieval-service;   uv run python -m pytest tests ; cd ..\..
cd services\ingestion_service;   uv run python -m pytest tests ; cd ..\..
```
Expect: all passing. They use fakes only.

## Building the missing BM25 index for `support`

The keyword index of a namespace is built and saved by the ingestion route when documents are uploaded to it. So
re-ingest the support documents through the normal upload (the gateway's ingestion upload, or the frontend), then run
`uv run python scripts/backfill.py --report-orphans`: `support` should now be compared instead of
`no keyword index stored`, and `uv run python scripts/backfill.py` (dry run) should show the new chunks. That upload writes to
Pinecone and Neon, so it is your decision to make. Until then retrieval for `support` is vector-only at every level (tested).
