# Evaluation Data Card

Fill in every field. Leave nothing implied: examiners read this to judge how far the scores can be trusted.

| Field | Value |
|---|---|
| Document sources (real vs synthetic) | |
| Who wrote the questions | |
| Dev / test split | |
| Number of no-answer questions | |
| Number of conflict questions | |

## Notes

- Document sources: name each corpus, say whether it is real or synthetic, and how the synthetic ones were produced.
- Who wrote the questions: author(s) and whether an LLM drafted any of them.
- Dev / test split: counts per split, and confirm that nothing was tuned on the test split.
- No-answer questions: questions whose answer is not in the corpus (the system should abstain).
- Conflict questions: questions where two sources disagree (the system should report both and flag review).
