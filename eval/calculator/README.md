# EKT extraction eval

Scores the calculator's **variable extraction** against the ground truth captured at Gate B
(`calculation_ground_truth` / `variable_corrections`). It does **not** score the final EP/GP price —
the calculation engine is deterministic, so grading the LLM-extracted inputs covers the model's error
surface without needing reference prices.

The grader (`server/scripts/eval_calculator/`) reads a project's saved gold, re-runs each position's
extraction with the **current** prompts (pinning the gold recipe at Gate A so the worklist is right),
and compares the system's fresh Gate B proposals to the endorsed values.

## Run

Needs the live stack (Postgres with gold rows, Elasticsearch with the project ingested, OpenRouter):

```bash
cd server
uv run python -m scripts.eval_calculator.run --project <project_uuid> [--abs-tol 0] [--limit N]
```

Results land in `eval/calculator/results/<project>-<timestamp>.{jsonl,summary.json}` (git-ignored).
The summary records the **prompt versions** used, so re-running after a prompt edit gives a clean
before/after — that's the regression signal.

## Metrics

Over the EINGABE (model-extracted) leaves only; SATZ/STAMMDATEN are catalog lookups and excluded.

- `classification_accuracy` — re-run's `leistung_key` vs. gold (Gate A, before the recipe is pinned).
- `value_accuracy` — of values that should be found, fraction matching gold within `--abs-tol`.
- `found_recall` — of values that should be found, fraction the re-run produced at all.
- `provenance_accuracy` — fraction with the right source (LANGTEXT/RAG), over **assessable** leaves
  only: a gold value the Kalkulator overrode carries `quelle=hitl`, not a real source, so it is not
  scored on provenance.

### Validity

A correction tagged `kalkulator_ermessen` (expert judgement) or `kontext_fehlt` (not in the
documents) is **not** a model error. The endorsed value still becomes gold, but those overrides are
expert/data signal, not extraction failures — keep that in mind when reading `value_accuracy`, and
filter `variable_corrections.reason` accordingly when analysing where the model actually went wrong.

## Chat-value extraction

Separately, `EKT_CHAT_VALUES` harvests the values the Kalkulator already stated in the pre-launch
chat (source 0). It is scored against **authored fixtures**, not the DB gold — each fixture is a
transcript plus the assignments it should yield. No retrieval or graph is needed, only the prompt.

```bash
cd server
uv run python -m scripts.eval_calculator.run_chat --dataset eval/calculator/chat_values/example.jsonl
```

Fixture format (JSONL, `//` lines ignored), names are `KONTEXT_VARIABLEN` keys, values verbatim in
the variable's own unit (the extractor does **no** conversion):

```json
{"id": "...", "transcript": [{"role": "user", "content": "..."}], "gold": {"tiefe_cm": "4"}}
```

Metrics are set-shaped over (name, value) assignments: `precision`/`recall`/`f1` (a hit needs the
right name *and* value), plus `name_recall` (did it find the name at all), `value_accuracy` (of names
found, value right), and `spurious` (names emitted that aren't in gold — e.g. a hallucinated or
off-catalog name). `example.jsonl` includes a no-values control fixture to check the model doesn't
invent assignments.
