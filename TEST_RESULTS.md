# Consolidated repository test and evaluation results

Compiled on **1 November 2026 (Asia/Calcutta)** from the results already saved in this repository. This consolidation did not run tests, call model providers, or change application code. Original artifacts are preserved.

This is the common entry point for local test suites, build/lint findings, live smoke checks, load tests, review regression probes, and historical RAG evaluation exports. Six timestamped run directories and three historical narrative reports were found. Directory names ending in `Z` use UTC; dates in the prose use IST unless explicitly stated.

## Latest verified status

The latest local run is `20261101T075415Z` (1 November, 13:24:15 IST). Its successful retry XML files take precedence over initial permission-related failures. Repeated runs are **not added together** as independent coverage.

| Check | Latest saved result | Evidence |
|---|---|---|
| Shared taxonomy, scripts, evaluation helpers | 65 passed | [Retry JUnit](test-results/20261101T075415Z/shared_scripts_eval_retry.xml) |
| Orchestrator | 87 passed | [Retry JUnit](test-results/20261101T075415Z/orchestrator_retry.xml) |
| Retrieval service | 65 passed | [JUnit](test-results/20261101T075415Z/retrieval_service.xml) |
| Ingestion service | 72 passed | [Retry JUnit](test-results/20261101T075415Z/ingestion_service_retry.xml) |
| Evaluation service | 1 passed | [JUnit](test-results/20261101T075415Z/evaluation_service.xml) |
| **Existing Python suites total** | **290 passed, 0 failed after retries** | Counts recalculated from the five JUnit suites above |
| API gateway | 19 tests passed, 10 failed; 10 suites passed, 11 failed, 21 total | [Jest output](test-results/20261101T075415Z/api_gateway.out) |
| Taxonomy validation | Passed | [Output](test-results/20261101T075415Z/taxonomy_check.out) |
| Frontend production build | Passed | Recorded in [verified report](test-results/20261101T075415Z/verified-summary.md); no separate build log saved |
| Gateway production build | Passed | Recorded in [verified report](test-results/20261101T075415Z/verified-summary.md); no separate build log saved |
| Frontend lint | 34 errors, 2 warnings | Recorded in [verified report](test-results/20261101T075415Z/verified-summary.md); no separate lint log saved |
| Additional review regression tests | **5 failed** | [Tests](test-results/20261101T075415Z/review_regression_test.py), [output](test-results/20261101T075415Z/review_regression.out) |
| Gateway behavior probes | Notification ownership gap and pending-session gap reproduced; foreign-session write blocked | [Probe](test-results/20261101T075415Z/gateway_probe.cjs), [output](test-results/20261101T075415Z/gateway_probe.out) |
| Live integration on 1 November | Not run: Docker Desktop Linux engine unavailable | [Verified report](test-results/20261101T075415Z/verified-summary.md) |

Across the existing Python and executed Jest tests, the latest run has **309 passed and 10 failed**, plus **one gateway suite that could not load**. The five additional review failures are separate from those existing-suite totals. Passing fake-service tests do not establish live system correctness.

The initial 1 November attempt had 17 pytest setup errors: shared/scripts/eval 14, orchestrator 1, ingestion 2. All were temporary-directory permission errors. Workspace-temporary-directory retries resolved them without application changes. See [initial summary](test-results/20261101T075415Z/summary.md), [verified summary](test-results/20261101T075415Z/verified-summary.md), and [corrected machine-readable results](test-results/20261101T075415Z/verified-results.json).

## Outstanding failures and behavior findings

| Finding | Evidence / qualification |
|---|---|
| Review edits concatenate old and revised answers | Regression produced `OriginalCorrected` instead of `Corrected` |
| Rejected reviews release the original answer | `approved=False` still clears the state review flag |
| Approved answer metadata remains marked for review | State flag becomes false while `final_answer.requires_human_review` stays true |
| Resume streaming forwards metadata JSON as answer text | Isolated generator probe emitted confidence JSON before the answer |
| Resume streaming duplicates the final answer | Isolated generator probe produced `Reviewed answerReviewed answer` |
| Review notifications lack caller ownership validation | Real controller method returned another user's resolved answer using fake dependencies; HTTP authentication was not exercised |
| Sessions awaiting review accept another message | `isSessionPending` checks session ownership but does not query unresolved reviews |
| Nonstream review resume sends the wrong field | Gateway sends `threadId`; Python requires `thread_id`. Source finding in latest verified report; validation failure reproduced in the earlier chat |
| Foreign-session chat writes are now blocked | Controller awaits ownership validation before writing; negative-path probe confirmed no write after denial |

The first five findings are captured in [review_regression.out](test-results/20261101T075415Z/review_regression.out). Gateway behavior is captured in [gateway_probe.out](test-results/20261101T075415Z/gateway_probe.out). These probes use fake dependencies and do not write to a live database.

### Existing gateway suite failures

Ten executed tests fail while building Nest testing modules because required dependencies are missing or not mocked. The affected specs are AuthController, AuthService, QueryController, QueryService, IngestionController, IngestionService, EvaluateController, EvaluateService, HealthController, and SessionService. The additional SessionController suite cannot load `uuid` under its Jest configuration (`SyntaxError: Unexpected token 'export'`). These setup failures prevent those tests from validating behavior; they do not themselves prove a production crash.

Some older reports say “nine scaffold failures plus one uuid failure.” Raw Jest output instead shows **ten failing executed tests plus one additional suite load error**. This consolidated report uses the raw totals.

## Saved run history

| Run directory / record | IST start or record time | Scope and outcome |
|---|---|---|
| [20261031T093250Z](test-results/20261031T093250Z/) | 31 Oct, 15:02:50 | Five Python suites: 290 passed. No gateway log or run summary saved in this directory |
| [20261031T093429Z](test-results/20261031T093429Z/) | 31 Oct, 15:04:29 | Python 290 passed; raw Jest 19 passed, 10 failed, one suite load error; taxonomy passed |
| [20261031T093710Z](test-results/20261031T093710Z/) | 31 Oct, 15:07:10 | Same existing-suite counts; summaries and raw artifacts saved |
| [20261031T093955Z](test-results/20261031T093955Z/) | 31 Oct, 15:09:55 | Same existing-suite counts; health, labeling dry run, six smoke cases, 1-user and 5-user load stages |
| [20261031T122224Z](test-results/20261031T122224Z/) | 31 Oct, 17:52:24 | Same existing-suite counts; six smoke cases, only 1-user load stage; corrected answer classification saved |
| [Evening narrative](docs/test-results/2026-10-31-evening-summary.md) | 31 Oct; final tree check 23:43 | Python 290 passed; same gateway failures; 12 smoke cases across LOCALIZE on/off; no load tests or raw logs saved for that evening record |
| [20261101T075415Z](test-results/20261101T075415Z/) | 1 Nov, 13:24:15 | Python 290 passed after retries; same gateway failures; builds passed, lint failed; five review probes failed; Docker unavailable |

The October narrative reports record commit `9fa327f46219d2fbadacbf3b7febc922b04b5326` on `refactor/frame-and-dag` with a dirty working tree. Existing container images were used during the evening smoke checks without rebuilding; their exact correspondence to local modifications was not established. The 1 November verified report does not attach a fresh commit hash.

## Historical live smoke results

### 31 October, 15:09 run

The [saved smoke JSON](test-results/20261031T093955Z/phase2_smoke.json) marks all six cases answered; answer correctness was not assessed, and the later answer-kind correction file is absent for this run.

| Domain / question | TTFT (s) | Total (s) | Recorded result |
|---|---:|---:|---|
| HR: How many casual leaves do I get? | 57.46 | 60.23 | answered |
| HR: Tell me about leave | 75.43 | 78.07 | answered |
| HR: Is PF deducted from my salary? | 74.62 | 77.27 | answered; no debug frame |
| Legal: What are the penalties under GDPR? | 102.58 | 105.28 | answered |
| Support: How do I reset my VPN password? | 69.10 | 71.78 | answered |
| Finance: How do I claim travel expenses? | 103.99 | 106.68 | answered |

**Configuration discrepancy:** this run's [health capture](test-results/20261031T093955Z/phase2_health.txt) reports `LOCALIZE=off` for both services, while its smoke JSON and narrative describe `on`. The records do not establish the exact transition timing. Do not use this run as a clean on/off comparison.

### 31 October, 17:52 rerun

Use [corrected answer kinds](test-results/20261031T122224Z/phase2_smoke_answer_kinds.json) instead of treating every nonempty stream in [original smoke JSON](test-results/20261031T122224Z/phase2_smoke.json) as a successful answer.

| Question | Corrected outcome | TTFT (s) | Total (s) |
|---|---|---:|---:|
| Casual leave | Real answer | 55.53 | 58.18 |
| Leave overview | Technical issue | 40.17 | 42.93 |
| PF deduction | Technical issue | 65.96 | 68.70 |
| GDPR penalties | Could not route | 58.74 | 61.42 |
| VPN password | Technical issue | 182.35 | 185.01 |
| Travel expenses | Could not route; stale support debug frame recorded | 17.69 | 20.34 |

Corrected total: **1 real answer, 3 technical fallbacks, 2 routing fallbacks**. The historical report attributes the provider failures to organization-level daily token exhaustion; no fresh quota check was performed during consolidation.

### 31 October evening on/off smoke

The [evening report](docs/test-results/2026-10-31-evening-summary.md) contains the only saved record of this run; separate raw outputs were not saved.

| Setting | Cases | Answered | Routing fallback | Errors |
|---|---:|---:|---:|---:|
| LOCALIZE on | 6 | 3 | 1 | 2: one timeout, one technical fallback |
| LOCALIZE off | 6 | 0 | 4 | 2 technical fallbacks |
| Total | 12 | 3 | 5 | 4 |

All 12 returned HTTP 201; the timeout did not complete at the client. Non-timeout requests emitted `[DONE]`. TTFT includes fallback text and is not necessarily time to a useful answer. These small, quota-affected observations do not establish localization quality or causality.

## Historical load results

Metrics below are read from saved Locust CSVs. Use `/query/stream` for actual stream request counts; TTFT and total-duration rows are synthetic metric events and must not be counted as additional HTTP requests. Times are converted from milliseconds to seconds.

| Run | Users | Stream requests | Failed | Failure rate | TTFT p50 / p95 (s) | Total p50 / p95 / p99 (s) |
|---|---:|---:|---:|---:|---|---|
| 31 Oct 15:09, stage 1 | 1 | 2 | 0 | 0% | 74 / 74 | 77 / 77 / 77 |
| 31 Oct 15:09, stage 2 | 5 | 5 | 5 | 100% | Not available | Not available |
| 31 Oct 17:52, stage 1 | 1 | 2 | 2 | 100% | 30 / 30, one token-bearing sample | 32 / 32 / 32, one completed sample |

The first run's prose reports p50 values of 72 s TTFT and 75 s total; the CSV's explicit `50%` column reports 74 s and 77 s. This table uses the explicit percentile columns. With only two samples, these are not reliable performance estimates.

The first 5-user stage recorded five ConnectionErrors. Its request durations of approximately 82–157 s are time until failure, not answer latencies. The rerun recorded one ConnectionError and one `classifier_failed`. The latter produced tokens but was still an application failure. No 10-user stage result exists. Further stages were stopped after exceeding the historical 30% failure threshold.

Historical narratives attribute the failure bottleneck to Groq daily token exhaustion and report low CPU/memory with no unplanned container restarts. The provider log excerpts are embedded in the reports, not saved as standalone provider logs. The classifier-fallback detection rule changed between the two runs, so their success rates are not directly comparable.

Sources: [first stage 1 CSV](test-results/20261031T093955Z/locust_stage1_stats.csv), [first stage 2 CSV](test-results/20261031T093955Z/locust_stage2_stats.csv), [rerun stage 1 CSV](test-results/20261031T122224Z/locust_stage1_stats.csv). HTML reports, failures, exceptions, histories, and resource snapshots are indexed below.

## Document-label dry runs

Historical live runs recorded the following dry-run totals. No labels were applied during those recorded checks.

| Namespace | Chunks | Would change | Failed |
|---|---:|---:|---:|
| legal | 233 | 233 | 0 |
| hr | 92 | 83 | 0 |
| engineering | 82 | 70 | 0 |
| finance | 142 | 141 | 0 |
| support | 54 | 51 | 0 |
| **Total** | **603** | **578** | **0** |

The `coding` namespace was not in the taxonomy and was left alone. Sources: [first output](test-results/20261031T093955Z/phase2_label_documents.out), [rerun output](test-results/20261031T122224Z/phase2_label_documents.out), [evening narrative](docs/test-results/2026-10-31-evening-summary.md).

## Historical RAG quality and calibration exports

These existing service-level exports have no explicit run identifier or evaluation date in their contents. They are historical artifacts, not results of the 1 November test run. Means below are recalculated directly from finite numeric CSV values; missing scores are excluded and their counts are shown.

| Artifact | Rows | Metric | Valid scores | Mean | Min–max |
|---|---:|---|---:|---:|---|
| [ragas_scores.csv](services/evaluation_service/ragas_scores.csv) | 14 | Faithfulness | 14 | 0.821053 | 0.200000–1.000000 |
| Same | 14 | Answer relevancy | 11 | 0.958835 | 0.894913–1.000000 |
| [callibration_check.csv](services/evaluation_service/callibration_check.csv) | 14 | Faithfulness | 14 | 0.786833 | 0.000000–1.000000 |
| Same | 14 | Answer relevancy | 14 | 0.964814 | 0.895229–1.000000 |
| Same | 14 | Reported confidence | 14 | 0.980714 | 0.970000–0.990000 |

`ragas_scores.csv` is missing answer-relevancy scores for data rows 10, 11, and 12 (rows numbered after the header). `callibration_check.csv` records `miscalibrated=True` for 1 of 14 rows and false for 13; these are stored flags, not a newly validated calibration definition. Its faithfulness values differ from the other export, so the two score sets must not be silently merged.

[ragas_results.json](services/evaluation_service/ragas_results.json) contains **15 answer records**, while each score CSV has **14 rows**. The count mismatch is unresolved. All 15 raw records have `ground_truth=null`; recorded namespaces include the historical `coding` domain. The files do not establish the current five-domain system's accuracy, a held-out split, or a contemporary benchmark.

[docs/data_card.md](docs/data_card.md) still has blank provenance/split fields. [eval/questions.example.jsonl](eval/questions.example.jsonl) is example input, not a result. No `eval/results/` output or completed frames evaluation result was found.

## Evidence corrections and remaining coverage

- Prefer latest successful retry XML over initial pytest temporary-directory errors. Preserve both attempts as history.
- Prefer raw Jest counts over older summaries' nine-versus-ten failure wording. One suite load failure is additional to ten failing executed tests.
- Prefer corrected smoke answer kinds over the rerun script's initial `answered` labels.
- Preserve the health-versus-LOCALIZE discrepancy rather than assuming an undocumented configuration transition.
- Historical HTTP 201, nonempty SSE tokens, or `[DONE]` do not by themselves prove a useful or correct answer. The evening report notes that orchestrator failures use fallback tokens rather than a typed error event.
- The latest frontend build success does not establish browser functionality. No frontend automated test suite or end-to-end browser result was saved.
- Live PostgreSQL/Pinecone/provider integration was exercised in historical smoke runs but was not reverified on 1 November because Docker was unavailable.
- Missing frames evaluation questions and absent 10-user load results remain coverage gaps. No new questions or measurements were invented for this consolidation.
- Build/lint outcomes and the evening run have narrative evidence but no separate raw logs. `test-results/` is ignored by Git; this root-level report provides a visible entry point, while linked raw artifacts may require separate inclusion when sharing the repository.

## Original artifact inventory

The following index includes every file directly inside the six saved run directories, every historical report under `docs/test-results`, and the three evaluation exports. Generated pytest temporary fixtures and caches are excluded because they are test inputs, not result artifacts.

### docs/test-results

| File | Type |
|---|---|
| [2026-10-31-evening-summary.md](docs/test-results/2026-10-31-evening-summary.md) | Narrative report |
| [2026-10-31-rerun-summary.md](docs/test-results/2026-10-31-rerun-summary.md) | Narrative report |
| [2026-10-31-summary.md](docs/test-results/2026-10-31-summary.md) | Narrative report |

### test-results/20261031T093250Z

| File | Type |
|---|---|
| [evaluation_service.out](test-results/20261031T093250Z/evaluation_service.out) | Execution output |
| [evaluation_service.xml](test-results/20261031T093250Z/evaluation_service.xml) | JUnit result |
| [ingestion_service.out](test-results/20261031T093250Z/ingestion_service.out) | Execution output |
| [ingestion_service.xml](test-results/20261031T093250Z/ingestion_service.xml) | JUnit result |
| [orchestrator.out](test-results/20261031T093250Z/orchestrator.out) | Execution output |
| [orchestrator.xml](test-results/20261031T093250Z/orchestrator.xml) | JUnit result |
| [retrieval_service.out](test-results/20261031T093250Z/retrieval_service.out) | Execution output |
| [retrieval_service.xml](test-results/20261031T093250Z/retrieval_service.xml) | JUnit result |
| [shared_scripts_eval.out](test-results/20261031T093250Z/shared_scripts_eval.out) | Execution output |
| [shared_scripts_eval.xml](test-results/20261031T093250Z/shared_scripts_eval.xml) | JUnit result |

### test-results/20261031T093429Z

| File | Type |
|---|---|
| [api_gateway.out](test-results/20261031T093429Z/api_gateway.out) | Execution output |
| [evaluation_service.out](test-results/20261031T093429Z/evaluation_service.out) | Execution output |
| [evaluation_service.xml](test-results/20261031T093429Z/evaluation_service.xml) | JUnit result |
| [ingestion_service.out](test-results/20261031T093429Z/ingestion_service.out) | Execution output |
| [ingestion_service.xml](test-results/20261031T093429Z/ingestion_service.xml) | JUnit result |
| [orchestrator.out](test-results/20261031T093429Z/orchestrator.out) | Execution output |
| [orchestrator.xml](test-results/20261031T093429Z/orchestrator.xml) | JUnit result |
| [retrieval_service.out](test-results/20261031T093429Z/retrieval_service.out) | Execution output |
| [retrieval_service.xml](test-results/20261031T093429Z/retrieval_service.xml) | JUnit result |
| [shared_scripts_eval.out](test-results/20261031T093429Z/shared_scripts_eval.out) | Execution output |
| [shared_scripts_eval.xml](test-results/20261031T093429Z/shared_scripts_eval.xml) | JUnit result |
| [summary.json](test-results/20261031T093429Z/summary.json) | Structured results |
| [summary.md](test-results/20261031T093429Z/summary.md) | Narrative report |
| [taxonomy_check.out](test-results/20261031T093429Z/taxonomy_check.out) | Execution output |

### test-results/20261031T093710Z

| File | Type |
|---|---|
| [api_gateway.out](test-results/20261031T093710Z/api_gateway.out) | Execution output |
| [evaluation_service.out](test-results/20261031T093710Z/evaluation_service.out) | Execution output |
| [evaluation_service.xml](test-results/20261031T093710Z/evaluation_service.xml) | JUnit result |
| [ingestion_service.out](test-results/20261031T093710Z/ingestion_service.out) | Execution output |
| [ingestion_service.xml](test-results/20261031T093710Z/ingestion_service.xml) | JUnit result |
| [orchestrator.out](test-results/20261031T093710Z/orchestrator.out) | Execution output |
| [orchestrator.xml](test-results/20261031T093710Z/orchestrator.xml) | JUnit result |
| [retrieval_service.out](test-results/20261031T093710Z/retrieval_service.out) | Execution output |
| [retrieval_service.xml](test-results/20261031T093710Z/retrieval_service.xml) | JUnit result |
| [shared_scripts_eval.out](test-results/20261031T093710Z/shared_scripts_eval.out) | Execution output |
| [shared_scripts_eval.xml](test-results/20261031T093710Z/shared_scripts_eval.xml) | JUnit result |
| [summary.json](test-results/20261031T093710Z/summary.json) | Structured results |
| [summary.md](test-results/20261031T093710Z/summary.md) | Narrative report |
| [taxonomy_check.out](test-results/20261031T093710Z/taxonomy_check.out) | Execution output |

### test-results/20261031T093955Z

| File | Type |
|---|---|
| [api_gateway.out](test-results/20261031T093955Z/api_gateway.out) | Execution output |
| [evaluation_service.out](test-results/20261031T093955Z/evaluation_service.out) | Execution output |
| [evaluation_service.xml](test-results/20261031T093955Z/evaluation_service.xml) | JUnit result |
| [ingestion_service.out](test-results/20261031T093955Z/ingestion_service.out) | Execution output |
| [ingestion_service.xml](test-results/20261031T093955Z/ingestion_service.xml) | JUnit result |
| [locust_stage1_exceptions.csv](test-results/20261031T093955Z/locust_stage1_exceptions.csv) | Metrics / data export |
| [locust_stage1_failures.csv](test-results/20261031T093955Z/locust_stage1_failures.csv) | Metrics / data export |
| [locust_stage1_stats.csv](test-results/20261031T093955Z/locust_stage1_stats.csv) | Metrics / data export |
| [locust_stage1_stats_history.csv](test-results/20261031T093955Z/locust_stage1_stats_history.csv) | Metrics / data export |
| [locust_stage2_exceptions.csv](test-results/20261031T093955Z/locust_stage2_exceptions.csv) | Metrics / data export |
| [locust_stage2_failures.csv](test-results/20261031T093955Z/locust_stage2_failures.csv) | Metrics / data export |
| [locust_stage2_stats.csv](test-results/20261031T093955Z/locust_stage2_stats.csv) | Metrics / data export |
| [locust_stage2_stats_history.csv](test-results/20261031T093955Z/locust_stage2_stats_history.csv) | Metrics / data export |
| [orchestrator.out](test-results/20261031T093955Z/orchestrator.out) | Execution output |
| [orchestrator.xml](test-results/20261031T093955Z/orchestrator.xml) | JUnit result |
| [phase2_health.txt](test-results/20261031T093955Z/phase2_health.txt) | Health / resource snapshot |
| [phase2_label_documents.out](test-results/20261031T093955Z/phase2_label_documents.out) | Execution output |
| [phase2_smoke.json](test-results/20261031T093955Z/phase2_smoke.json) | Structured results |
| [phase3_docker_after.txt](test-results/20261031T093955Z/phase3_docker_after.txt) | Health / resource snapshot |
| [phase3_docker_before.txt](test-results/20261031T093955Z/phase3_docker_before.txt) | Health / resource snapshot |
| [retrieval_service.out](test-results/20261031T093955Z/retrieval_service.out) | Execution output |
| [retrieval_service.xml](test-results/20261031T093955Z/retrieval_service.xml) | JUnit result |
| [shared_scripts_eval.out](test-results/20261031T093955Z/shared_scripts_eval.out) | Execution output |
| [shared_scripts_eval.xml](test-results/20261031T093955Z/shared_scripts_eval.xml) | JUnit result |
| [stage1.html](test-results/20261031T093955Z/stage1.html) | Locust HTML report |
| [stage2.html](test-results/20261031T093955Z/stage2.html) | Locust HTML report |
| [summary.json](test-results/20261031T093955Z/summary.json) | Structured results |
| [summary.md](test-results/20261031T093955Z/summary.md) | Narrative report |
| [taxonomy_check.out](test-results/20261031T093955Z/taxonomy_check.out) | Execution output |

### test-results/20261031T122224Z

| File | Type |
|---|---|
| [api_gateway.out](test-results/20261031T122224Z/api_gateway.out) | Execution output |
| [evaluation_service.out](test-results/20261031T122224Z/evaluation_service.out) | Execution output |
| [evaluation_service.xml](test-results/20261031T122224Z/evaluation_service.xml) | JUnit result |
| [ingestion_service.out](test-results/20261031T122224Z/ingestion_service.out) | Execution output |
| [ingestion_service.xml](test-results/20261031T122224Z/ingestion_service.xml) | JUnit result |
| [locust_stage1_exceptions.csv](test-results/20261031T122224Z/locust_stage1_exceptions.csv) | Metrics / data export |
| [locust_stage1_failures.csv](test-results/20261031T122224Z/locust_stage1_failures.csv) | Metrics / data export |
| [locust_stage1_stats.csv](test-results/20261031T122224Z/locust_stage1_stats.csv) | Metrics / data export |
| [locust_stage1_stats_history.csv](test-results/20261031T122224Z/locust_stage1_stats_history.csv) | Metrics / data export |
| [orchestrator.out](test-results/20261031T122224Z/orchestrator.out) | Execution output |
| [orchestrator.xml](test-results/20261031T122224Z/orchestrator.xml) | JUnit result |
| [phase2_health.txt](test-results/20261031T122224Z/phase2_health.txt) | Health / resource snapshot |
| [phase2_label_documents.out](test-results/20261031T122224Z/phase2_label_documents.out) | Execution output |
| [phase2_smoke.json](test-results/20261031T122224Z/phase2_smoke.json) | Structured results |
| [phase2_smoke_answer_kinds.json](test-results/20261031T122224Z/phase2_smoke_answer_kinds.json) | Structured results |
| [phase3_docker_after.txt](test-results/20261031T122224Z/phase3_docker_after.txt) | Health / resource snapshot |
| [phase3_docker_before.txt](test-results/20261031T122224Z/phase3_docker_before.txt) | Health / resource snapshot |
| [retrieval_service.out](test-results/20261031T122224Z/retrieval_service.out) | Execution output |
| [retrieval_service.xml](test-results/20261031T122224Z/retrieval_service.xml) | JUnit result |
| [shared_scripts_eval.out](test-results/20261031T122224Z/shared_scripts_eval.out) | Execution output |
| [shared_scripts_eval.xml](test-results/20261031T122224Z/shared_scripts_eval.xml) | JUnit result |
| [stage1.html](test-results/20261031T122224Z/stage1.html) | Locust HTML report |
| [summary.json](test-results/20261031T122224Z/summary.json) | Structured results |
| [summary.md](test-results/20261031T122224Z/summary.md) | Narrative report |
| [taxonomy_check.out](test-results/20261031T122224Z/taxonomy_check.out) | Execution output |

### test-results/20261101T075415Z

| File | Type |
|---|---|
| [api_gateway.out](test-results/20261101T075415Z/api_gateway.out) | Execution output |
| [evaluation_service.out](test-results/20261101T075415Z/evaluation_service.out) | Execution output |
| [evaluation_service.xml](test-results/20261101T075415Z/evaluation_service.xml) | JUnit result |
| [gateway_probe.cjs](test-results/20261101T075415Z/gateway_probe.cjs) | Reproduction probe |
| [gateway_probe.out](test-results/20261101T075415Z/gateway_probe.out) | Execution output |
| [ingestion_service.out](test-results/20261101T075415Z/ingestion_service.out) | Execution output |
| [ingestion_service.xml](test-results/20261101T075415Z/ingestion_service.xml) | JUnit result |
| [ingestion_service_retry.xml](test-results/20261101T075415Z/ingestion_service_retry.xml) | JUnit result |
| [orchestrator.out](test-results/20261101T075415Z/orchestrator.out) | Execution output |
| [orchestrator.xml](test-results/20261101T075415Z/orchestrator.xml) | JUnit result |
| [orchestrator_retry.out](test-results/20261101T075415Z/orchestrator_retry.out) | Execution output |
| [orchestrator_retry.xml](test-results/20261101T075415Z/orchestrator_retry.xml) | JUnit result |
| [retrieval_service.out](test-results/20261101T075415Z/retrieval_service.out) | Execution output |
| [retrieval_service.xml](test-results/20261101T075415Z/retrieval_service.xml) | JUnit result |
| [review_regression.out](test-results/20261101T075415Z/review_regression.out) | Execution output |
| [review_regression_test.py](test-results/20261101T075415Z/review_regression_test.py) | Reproduction test |
| [shared_scripts_eval.out](test-results/20261101T075415Z/shared_scripts_eval.out) | Execution output |
| [shared_scripts_eval.xml](test-results/20261101T075415Z/shared_scripts_eval.xml) | JUnit result |
| [shared_scripts_eval_retry.out](test-results/20261101T075415Z/shared_scripts_eval_retry.out) | Execution output |
| [shared_scripts_eval_retry.xml](test-results/20261101T075415Z/shared_scripts_eval_retry.xml) | JUnit result |
| [summary.json](test-results/20261101T075415Z/summary.json) | Structured results |
| [summary.md](test-results/20261101T075415Z/summary.md) | Narrative report |
| [taxonomy_check.out](test-results/20261101T075415Z/taxonomy_check.out) | Execution output |
| [verified-results.json](test-results/20261101T075415Z/verified-results.json) | Structured results |
| [verified-summary.md](test-results/20261101T075415Z/verified-summary.md) | Narrative report |

### services/evaluation_service

| File | Type |
|---|---|
| [callibration_check.csv](services/evaluation_service/callibration_check.csv) | Metrics / data export |
| [ragas_results.json](services/evaluation_service/ragas_results.json) | Structured results |
| [ragas_scores.csv](services/evaluation_service/ragas_scores.csv) | Metrics / data export |

