# Adding a New Prompt Type

A prompt type is declared **once** in the backend enum and then mirrored across the database,
the seed files, a load site, the generated TypeScript types, and a couple of hardcoded UI lists.
Miss one and you get a DB `IntegrityError`, a failed seed, a red `tsc` build, or a stale dropdown.
This is the end-to-end checklist.

## Mental model

`PromptType` in `server/shared/models/enums.py` is the **single source of truth**. Everything else
must agree with it:

- a seed `.prompt` file whose **filename stem equals the enum value**,
- two DB `CHECK` constraints (auto for a fresh DB, a manual migration for an existing one),
- a runtime **load site** (how the prompt is fetched),
- the generated TS union (regenerated) plus two hardcoded UI lists,
- two lock tests.

The enum member's **value** (e.g. `"project_context_resolve"`) is the contract string used
everywhere — the `.prompt` filename, the DB `prompt_type` column, and the TS union member.

## TL;DR checklist

- [ ] 1. Add the member to `PromptType` (`server/shared/models/enums.py`).
- [ ] 2. Add `server/scripts/seed/prompts/<value>.prompt` (stem **must** equal the enum value).
- [ ] 3. Wire a load site (+ an LLM call site if it's a structured-output prompt).
- [ ] 4. Add a `sql/NN_*.sql` migration widening **both** `prompt_type` CHECK constraints.
- [ ] 5. Apply the migration to the main DB, then seed.
- [ ] 6. Update the two lock tests.
- [ ] 7. Regenerate the TS types + update the hardcoded UI lists, then rebuild.
- [ ] 8. Run the full test suite.

---

## 1. Backend enum (source of truth)

Add the member to `PromptType` in `server/shared/models/enums.py`:

```python
class PromptType(StrEnum):
    ...
    EKT_OUTPUT_NARRATE = "ekt_output_narrate"
    MY_NEW_PROMPT = "my_new_prompt"   # <-- value is the contract string used everywhere
```

Nothing else in the backend needs a manual enum edit: `db/tables/prompt_versions.py` and
`db/tables/conversations.py` build their CHECK constraints from the enum automatically
(`_PROMPT_TYPES_SQL = ", ".join(...)`), and the TS union is derived from the enum via the schema
export. Those are handled by later steps (a fresh-DB CHECK, and `gen:types`).

## 2. Seed prompt file

Create `server/scripts/seed/prompts/my_new_prompt.prompt`. The **filename stem must equal the enum
value** — the seed loader maps stem → `PromptType(path.stem)` and errors on a mismatch.

```
---
model_name: openai/gpt-5.4
temperature: null
top_p: null
reasoning_effort: low
---
<the system prompt body, including any {{placeholder}} templates>
```

- `prompt_type` and `system_prompt` are **derived** (filename + body) — do not put them in the
  frontmatter.
- This file is **required**: `tests/unit/prompts/test_seed_prompts.py::test_shipped_prompt_files_cover_every_prompt_type`
  asserts every `PromptType` except `EKT_CALCULATOR` has a `.prompt` file.

> **Exception — conversation / StateGraph discriminators.** A `PromptType` that only tags a
> *conversation* (like `EKT_CALCULATOR`) and is never seeded as its own prompt does **not** get a
> `.prompt` file. Add it to `CONVERSATION_DISCRIMINATORS` (in `enums.py`) instead, and skip the
> seed + load-site steps. See [StateGraph / conversation discriminators](#stategraph--conversation-discriminators)
> for the full recipe.

## 3. Load site (how the prompt is fetched at runtime)

Pick one pattern:

- **Independent / lazy loader (preferred for a prompt used by one service).** Mirror
  `server/shared/services/project_context/prompts.py::load_resolve_prompt`: a small
  `load_<x>_prompt(conn)` that calls `PromptVersionRepository(conn).get_latest(PromptType.MY_NEW_PROMPT)`
  and raises a clear "not seeded" error. This keeps an unseeded prompt from breaking unrelated flows.
- **Eager calculator bundle.** If it's a per-position calculator prompt, add it to `EKT_PROMPT_TYPES`
  in `server/shared/services/calculator/prompts.py` (loaded up front by `load_calculator_prompts`;
  a missing version raises `CalculatorPromptNotSeededError`).

If the prompt produces **structured output**, add an LLM call site that passes an `output_model`
to `llm.chat_with_reasoning(...)` — see `server/shared/services/project_context/llm.py` or
`server/shared/services/calculator/llm_calls.py`.

## 4. DB CHECK constraints (the gotcha)

`prompt_versions` and `conversations` each have a CHECK that enumerates the **full** `PromptType`
enum:

| Table | Constraint name |
|---|---|
| `prompt_versions` | `ck_prompt_versions_prompt_type_valid` |
| `conversations` | `ck_conversations_conversation_prompt_type_valid` |

A **fresh** database gets the new value automatically (the table defs build the CHECK from the
enum, and `metadata.create_all` runs on boot). But **`create_all(checkfirst=True)` never ALTERs an
existing table** — so an existing DB keeps the stale CHECK, and seeding/inserting the new
`prompt_type` fails with an `IntegrityError`.

For existing DBs, add `sql/NN_my_new_prompt_type.sql` (next free number; the `NN_a`/`NN_b` suffix
convention exists if a number is taken). Template: `sql/08_kalkulation_v2_prompt_types.sql` and
`sql/09_project_context_prompt_types.sql`. Drop + re-add **both** constraints with the current enum
values **plus any legacy values already present in the DB** (so existing rows aren't rejected):

```sql
-- sql/NN_my_new_prompt_type.sql
-- Widen both prompt_type CHECK constraints for my_new_prompt.
-- create_all(checkfirst) never alters an existing table, so the enum-derived CHECK goes stale;
-- seeding the new prompt fails the CHECK until this runs. Retains the legacy ekt_* values so an
-- already-migrated DB's existing rows still satisfy the constraint. Idempotent; run after <prev>.

ALTER TABLE prompt_versions DROP CONSTRAINT IF EXISTS ck_prompt_versions_prompt_type_valid;
ALTER TABLE prompt_versions ADD CONSTRAINT ck_prompt_versions_prompt_type_valid
    CHECK (prompt_type IN (<full current enum list>, 'my_new_prompt', <legacy values>));

ALTER TABLE conversations DROP CONSTRAINT IF EXISTS ck_conversations_conversation_prompt_type_valid;
ALTER TABLE conversations ADD CONSTRAINT ck_conversations_conversation_prompt_type_valid
    CHECK (prompt_type IN (<full current enum list>, 'my_new_prompt', <legacy values>));
```

Widen **both** even though a `conversations.prompt_type` is only ever a conversation discriminator
(e.g. `project_chat`, `ekt_calculator`): keeping them in lockstep matches what a fresh `create_all`
builds, and follows the established `sql/08` precedent.

> The `_test` database needs no migration — the test suite rebuilds its schema from `create_all`
> each session, so it already has the current CHECK.

## 5. Apply the migration, then seed

Order matters: migrate the main DB **before** seeding, or the seed `INSERT` fails the CHECK.

```bash
# 1) Widen the CHECK on the main DB (one-time). Pipes the host SQL into the container's psql.
docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
  < sql/NN_my_new_prompt_type.sql

# 2) Seed. NOT idempotent: appends a new version for EVERY .prompt file (the app reads get_latest).
docker compose exec -T api python -m scripts.seed.prompts
```

You should see `my_new_prompt: added v1` in the output.

## 6. Tests to update

- `tests/unit/models/test_models.py::test_enum_values` — a **lock test** on the exact `PromptType`
  set. Add `"my_new_prompt"` to the expected set.
- `tests/unit/prompts/test_seed_prompts.py::test_shipped_prompt_files_cover_every_prompt_type` —
  passes automatically **once the `.prompt` file exists** (no edit needed, unless the new type is a
  conversation discriminator, in which case add it to the exclusion set).

Run `uv run pytest tests/unit/models tests/unit/prompts` to confirm, then the full suite (step 8).

## 7. Frontend

The TS `PromptType` union is derived from the enum via the schema export, so regenerating picks up
the new value. Two hardcoded lists must then be reconciled with it:

```bash
npm --prefix ui run gen:types   # regenerates ui/src/types/generated.ts (adds the union member)
```

- `ui/src/views/workspace/tools/PromptList.tsx` — `TYPE_COLOR` is a
  `Record<PromptType, BadgeColor>`, so it must have **every** key. **You must add a color** for the
  new value or `tsc` fails (missing property).
- `ui/src/views/workspace/tools/promptFile.ts` — `PROMPT_TYPES` validates importable prompt-file
  stems. Add the new value **if** the prompt is user-editable/importable via the prompt editor.
  (A subset is allowed by the type, so omitting it won't fail `tsc`, but importing the file would be
  rejected.)
- `ui/src/views/main/ExecutionLogView.tsx` — `PROMPT_TYPES` is a plain `string[]` log filter.
  Add the value so the new prompt's execution-log rows are filterable. (Won't break the build.)

```bash
npm --prefix ui run build       # tsc + vite; must be clean
```

> `gen:types` runs on the host and needs `uv sync` + `npm --prefix ui ci` (for `json2ts`).

## 8. Verify

```bash
uv run pytest                   # all green; lock tests updated
npm --prefix ui run build       # tsc + bundle clean
```

Then smoke-test the actual prompt path (e.g. hit the service that loads it) against a seeded DB.

---

## StateGraph / conversation discriminators

`PromptType` does **double duty**. Most members name a **seeded prompt** (a `.prompt` file whose
text an LLM call executes). But a few members are **discriminators**: they tag *which agent /
StateGraph owns a conversation*, and are stored in `conversations.prompt_type`. `EKT_CALCULATOR` is
the canonical example — a position chat that owns a calculator graph run. It has no `.prompt` file
and is never executed as a prompt; the chat itself runs on `PROJECT_CHAT`, and the graph's own nodes
call their specific seeded prompts (`ekt_leistung_classify`, `ekt_chat_values`, …).

Cleanly splitting these two concerns (e.g. a separate `ConversationKind` enum) is a large refactor —
it would ripple through the enum, both CHECK constraints, the generated types, and the UI — so for
now they share one enum, and the discriminators are grouped explicitly:

```python
# server/shared/models/enums.py
CONVERSATION_DISCRIMINATORS: frozenset[PromptType] = frozenset({PromptType.EKT_CALCULATOR})
```

This constant is the **single source of truth** for "which prompt types are discriminators, not
seeded prompts." `tests/unit/prompts/test_seed_prompts.py` enforces it:

```python
expected = set(PromptType) - CONVERSATION_DISCRIMINATORS   # every seeded type ships a .prompt file
```

So if you add a discriminator and forget the constant, the seed-coverage test fails (it expects a
`.prompt` file that doesn't exist) — forcing you to make an explicit choice.

### Two levels of tagging (why this coexists cleanly)

- **Conversation owner** — `conversations.prompt_type`. Set to a discriminator (`ekt_calculator`) or
  a chat prompt (`project_chat`). Says *which agent/graph drives this conversation*.
- **Per-call prompt** — the `chat_prompt_type` passed to `llm.chat_with_reasoning(...)` at each
  StateGraph node. Set to the specific **seeded** prompt that call executes
  (`ekt_leistung_classify`, …), for the execution log.

A StateGraph therefore has **one** discriminator (the conversation owner) and **many** seeded
prompts (its nodes). Adding a new StateGraph is exactly this pattern.

### Recipe: adding a new StateGraph discriminator

Say you build a new `foo_agent` StateGraph and want to tag its conversations `FOO_AGENT`:

1. Add `FOO_AGENT = "foo_agent"` to `PromptType` (§1).
2. Add it to `CONVERSATION_DISCRIMINATORS` in `enums.py`.
3. **Skip** the `.prompt` file (§2), the seed, and the load site — a discriminator is not a prompt.
4. **Do** add the CHECK-constraint migration (§4) — `foo_agent` is a real value that lands in
   `conversations.prompt_type`, so both CHECKs must accept it.
5. **Do** add it to `TYPE_COLOR` in `PromptList.tsx` (§7) — the `Record<PromptType, …>` needs every
   key — and regenerate the TS types.
6. Its own graph nodes' LLM prompts are ordinary **seeded** prompt types — each follows the full
   §1–§7 flow (enum + `.prompt` file + load site + …).

In short: a discriminator skips the *prompt* half (seed file, load site, coverage test) but keeps
the *value* half (enum, CHECK constraints, TS union + color map).

## Appendix — every place a prompt type appears

| Where | File | Action |
|---|---|---|
| Enum (source of truth) | `server/shared/models/enums.py` | **Edit** — add the member |
| Discriminator grouping | `server/shared/models/enums.py` (`CONVERSATION_DISCRIMINATORS`) | **Edit** — only if it's a StateGraph/conversation discriminator |
| Seed prompt | `server/scripts/seed/prompts/<value>.prompt` | **Add** — stem == value (skip for discriminators) |
| Fresh-DB CHECK (prompt_versions) | `server/shared/db/tables/prompt_versions.py` | Auto (built from enum) |
| Fresh-DB CHECK (conversations) | `server/shared/db/tables/conversations.py` | Auto (built from enum) |
| Existing-DB migration | `sql/NN_*.sql` | **Add** — widen both CHECKs |
| Load site | `services/*/prompts.py` (+ `services/*/llm.py`) | **Add/edit** — loader (+ call site) |
| Enum lock test | `tests/unit/models/test_models.py` | **Edit** — add to expected set |
| Seed-coverage test | `tests/unit/prompts/test_seed_prompts.py` | Auto (once the `.prompt` exists) |
| Generated TS union | `ui/src/types/generated.ts` | **Regenerate** (`gen:types`) |
| UI color map | `ui/src/views/workspace/tools/PromptList.tsx` | **Edit** — add a color (required) |
| UI import validation | `ui/src/views/workspace/tools/promptFile.ts` | **Edit** — if seedable/importable |
| UI log filter | `ui/src/views/main/ExecutionLogView.tsx` | **Edit** — optional, for filtering |
