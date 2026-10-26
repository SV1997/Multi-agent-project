# Localization evaluation

Compares the four `LOCALIZE` levels on a fixed set of questions.

| level  | what is on |
|--------|------------|
| off    | nothing - the system as it was before this work |
| filter | the question is sorted into a frame and the search only looks inside that frame's categories |
| prompt | filter + the answering prompt gets the category instructions |
| full   | prompt + a clarifying question when a needed detail is missing |

## 1. Write the question set (you)

Copy `questions.example.jsonl` to `questions.jsonl` and replace the three EXAMPLE rows with real questions.
The expected frame, categories, clarification flag and reference answer must come from the policy documents,
written by you. One JSON object per line; see `questions.py` for what each field means and what is checked.
Put roughly half the questions in `"split": "tune"` (you may look at these while editing frames and prompts) and
half in `"heldout"` (do not look at them until the end - they show whether the tuning generalises).

Check the file without running anything:

    uv run python eval/localize/runner.py report --questions eval/localize/questions.jsonl

## 2. Run each level

`LOCALIZE` is a setting of the running services, so start the stack once per level (compose passes it to the
orchestrator and the retrieval service; the default is `off`):

    $env:LOCALIZE = "filter"
    docker compose up -d --build --no-deps orchestrator retrieval-service
    $env:INTERNAL_SHARED_SECRET = "<same value as the orchestrator>"
    $env:EVAL_EMPLOYEE_EMAIL = "<an employee e-mail allowed to read all five domains>"
    uv run python eval/localize/runner.py run --level filter --questions eval/localize/questions.jsonl

Repeat for `off`, `prompt` and `full`. Each run stores `results/<level>.json` (git-ignored). The runner warns if
the answers do not look like the level you named (for example frames present when you said `off`).

## 3. Compare

    uv run python eval/localize/runner.py report --questions eval/localize/questions.jsonl

## What the numbers mean

- **wrong-category citations** - of the cited sources whose categories are known, the share whose categories share
  nothing with the question's expected categories. Sources in documents with mixed categories are not judged.
- **frame accuracy** - questions sorted into exactly the expected frame (no frame counts as wrong).
- **clarification correct** - asked a clarifying question exactly when one was needed (only `full` asks).
- **fallback rate** - questions whose evidence came from a widened search.
- **gap** - tune minus held-out.

`n/a` means the level cannot measure it (for example `off` has no frames); it is not zero.

## Tests

    uv run python -m pytest eval/localize/tests

They use made-up results and a fake orchestrator; they say nothing about how well the real system performs.
