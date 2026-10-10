# Task 02: Several LV documents per project (UI)

Depends on: 01 (per-document routes, no LV replace). Parallel with 03, 04, 05.

## Use a worktree

Preflight, on `main` before creating the worktree. If this fails, the dependency is
not merged yet: stop and report instead of re-doing the other task's work.

```bash
test -f sql/18_multi_lv_documents.sql   # task 01 merged
```

Work in a dedicated git worktree and branch, never in the main checkout:

```bash
git worktree add ../swa-task02 -b task/02-multi-lv-ui
```

Follow the "Worktree setup" section of `tasks/README.md` for the rest: per-worktree
`uv sync` and `npm ci`, your own test database (`POSTGRES_DB=roadbuilders_t02`
for pytest), one shared compose stack that you never start or restart, migrations
verified on a scratch database only, and no commits unless asked.

## Goal

The project page lets the user pick which LV document the "LV Positions" and "LV-Texte"
tabs show, and the upload copy no longer claims that a GAEB file replaces the project's LV.

## Current state

- `ui/src/views/main/ProjectDetails.tsx` renders tabs `lv | texts | documents | context`;
  `LVItemsTable` and `LVTextsPanel` take only `projectUuid` and call
  `useProjectLvItems` / `useProjectLvTexts` (`ui/src/api/projects.ts`).
- `useLvItemSearch(projectUuid, q)` is project-wide; `LVItem` rows carry `document_uuid`.
- `ui/src/views/main/UploadDocumentDialog.tsx` and `ui/src/lib/documentType.ts` say a GAEB
  file "is the LV document" / replaces it.
- `ui/src/api/ingest.ts::useProjectIngestStatus` invalidates only `projectKeys.lvItems` on
  `ingest_completed`.
- Shared UI primitives live in `ui/src/components/ui/` (`listbox.tsx`, `select.tsx`,
  `badge.tsx`, ...). Tailwind only.

## Changes

### API hooks (`ui/src/api/projects.ts`)
- Add `projectKeys.documentLvItems(projectUuid, documentUuid)` and
  `documentLvTexts(...)`, with hooks `useDocumentLvItems(projectUuid, documentUuid)` and
  `useDocumentLvTexts(...)` calling the per-document routes from task 01. `enabled` only
  when both ids are set.
- Keep the project-wide hooks for other callers.

### LV document selector
- In `ProjectDetails.tsx`, derive `lvDocuments = docs.filter(d => d.document_type ===
  "LV_DOCUMENT")` (use the `DOCUMENT_TYPE_LV` constant from `lib/documentType.ts`, not a
  literal). Hold `selectedLvDocumentUuid` in component state; default to the most recently
  added LV document; reset when the selected one disappears (derive, do not `useEffect`).
- Render a selector (`Listbox` from `components/ui/listbox.tsx`) above the LV tabs only
  when `lvDocuments.length > 1`; with exactly one, show its file name as a small label;
  with none, the tabs show the existing empty state.
- `LVItemsTable` and `LVTextsPanel` take `documentUuid: string | undefined` in addition to
  `projectUuid` and use the per-document hooks. When `documentUuid` is undefined render the
  current empty state ("no LV document yet").
- Search: keep `useLvItemSearch` project-wide, filter results client-side to the selected
  `document_uuid`, and show a one-line hint with the count hidden by the filter if any.
- The "Position Chat" / calculator launch from a row already passes `lv_item_uuid`, so it is
  document-safe without changes. Verify by reading `useRunCalculation`.

### Copy and status
- `UploadDocumentDialog.tsx` + the header comment in `lib/documentType.ts`: a GAEB file
  becomes a new LV document; several LV documents per project are allowed.
- `useProjectIngestStatus`: on `ingest_completed` also invalidate `projectKeys.lvTexts(uuid)`
  and the two per-document keys (invalidate by prefix `['project', uuid]` if that is simpler
  and does not refetch too much; check what else hangs under that prefix first).
- Documents tab: no structural change. Optional: a small "LV" count badge in the tab label
  when more than one LV document exists.

### Types
- Run `npm run gen:types` after task 01 lands and fix any `ScopeTrace.lv_document_uuid`
  consumer (grep `lv_document_uuid` in `ui/src`).

## Checks
- `cd ui && npx tsc --noEmit -p tsconfig.app.json && npx eslint <changed files>`.
- Drive the UI headlessly (playwright-core + system Chrome, see the pattern in the session
  notes: `chromium.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/
  Google Chrome', headless: true })`, open `http://localhost:5173/`, click "View Project",
  open a project) on a project with two LV documents and confirm switching the selector
  swaps the positions and the texts. Screenshot before/after and keep the data untouched.

## Done when
- A project with two GAEB files shows a selector; each tab shows only the selected
  document's rows; a project with one or zero LV documents looks as it does today.
- No TypeScript `any`; types regenerated; eslint clean.
