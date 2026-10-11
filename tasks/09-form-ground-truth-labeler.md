# Task 09: Ground-truth labeler for Formblätter and a one-off measurement script

Depends on: 07 (form documents) merged on main (`b2969f1`), for `extract_source_lines`,
`detect_form_kind` and `classify_form_role`. Independent of 08; 08's "Done means" consumes
this task's labels and script, so run 09 first or in parallel.

## Use a worktree

Preflight, on `main` before creating the worktree:

```bash
test -d server/shared/services/ingestion/forms && test -d server/training
```

```bash
git worktree add ../swa-task09 -b task/09-form-labeler
```

Follow the "Worktree setup" section of `tasks/README.md`. This task touches no database
table, no migration, no UI under `ui/`, and no production code path. It adds a
dependency group, a Streamlit tool, label files and one script.

## Goal

Checkbox state in Formblätter is the input to yes/no answers such as "Sind Nebenangebote
zugelassen?", and today it is lost or misread (see task 08, "Evidence"). Before and after
task 08 we need a number, not an impression. This task delivers:

- a local **labeling tool** that shows a form page as an image next to the pipeline's own
  extracted lines, lets Arthur mark each line as *no box / unchecked / checked*, and
  collects per tender a list of **fact questions with gold answers and Fundstelle**;
- the **label files** for at least three tenders in the repo;
- a **one-off script** that scores a toggle detector against the box labels and the
  running chat API against the fact labels, and prints a table. Not the eval runner.

## Evidence this is built on (2026-10-11)

- The pipeline's line extraction (`extract_source_lines`, poppler `pdftotext
  -bbox-layout`) emits one line per visual line with a top-origin bbox. Tick glyphs and
  section numbers come out as separate lines ("6.1", "X") next to their label line. The
  labeler must show these lines as they are so labels match what 08 will see.
- A page of HVA 111 has 17 boxes; a Vergabestelle form has 3-5 pages; a tender has 5-7
  Vergabestelle forms. Full box labels for three tenders are roughly 1,000 tri-state
  decisions; with proposals pre-filled it is roughly 100 corrections plus a visual pass.
- `pdf2image` (poppler) renders the thumbnails in production and renders the HVA forms
  correctly (fonts are embedded: `LiberationSans`). The earlier LV-matching tool in
  `server/training` moved to PyMuPDF because poppler drew tofu for a non-embedded Calibri;
  PyMuPDF is AGPL and not a dependency here, so this tool uses `pdf2image` and the
  labeler reports a page as unreadable rather than switching renderers.
- `eval/` already holds hand-made reference data (`truth.json`, `questions.csv`,
  `projects.json`); `server/training` is gitignored and has its own uv project with the
  Streamlit LV-matching tool (`match_pdfs_app.py`), whose sidebar-button-list pattern
  works well for a "next unlabelled item" flow.
- Arthur's decisions (2026-10-11): labels and measurement are a one-off script, not the
  eval runner; unchecked options are dropped from chunks (so the fact labels must be
  answerable from checked options alone).

## Decisions already made (do not re-litigate)

1. **Labels are files in the repo**, under `eval/forms/`, one JSON per labelled PDF and
   one per tender for facts. Diffable, reviewable, no database, no API. They can be
   imported into `rag_ground_truth` later if the eval runner is adopted; nothing here
   depends on that.
2. **Line identity is the pipeline's own output.** The tool calls
   `extract_source_lines(pdf_bytes, uuid4())` and shows every line of the page with its
   bbox. A label stores `page`, `bbox`, `text` of the line, never a `line_id` (08 merges
   marginal tokens, which renumbers lines). The script matches a detector line to a label
   by page, bbox overlap and text containment, so a merged line ("6.1 Nebenangebote sind
   nicht zugelassen ...") still matches the label on the original label line.
3. **Tri-state per line**: `none` (no box in front of this line), `unchecked`, `checked`.
   Default `none`. A tick glyph line ("X") itself is never labelled; the state belongs to
   the label line it sits in front of.
4. **Proposals are allowed but visible.** The tool may pre-fill `unchecked`/`checked`
   from a small geometric heuristic kept inside the tool (`proposals.py`: pdfplumber
   squares 6-12pt, tick glyph inside, nearest line to the right). It is a labeling aid,
   not the detector under test; 08 writes its own. Proposed values are shown in a
   distinct colour until the labeler confirms the page, and a page counts as labelled only
   after an explicit "Seite bestätigen". The bias is accepted because the page image sits
   next to the list.
5. **Facts are questions a Kalkulator asks, answerable from checked options and filled
   fields of Vergabestelle forms.** Each fact has a `kind`: `yes_no` (gold is `ja` or
   `nein`), `value` (gold is a short string, e.g. `31.12.2026`, `5 %`), `list` (gold is a
   list of short strings). Scope is the Vergabestelle forms; prose documents are out of
   scope for the gold Fundstelle even when they repeat the fact (the Baubeschreibung also
   says Nebenangebote are not allowed; the Fundstelle is the 111 form).
6. **Streamlit via a dependency group**, not the main dependency set. `pyproject.toml`
   gains `[dependency-groups] tools = ["streamlit>=1.40"]`; run with `uv run --group
   tools streamlit run server/scripts/form_labeler/app.py`. The tool reads
   `server/training` directly; it never touches Postgres, ES or MinIO.
7. **Measurement runs against the compose stack**, the way a user uses it: facts are
   asked through `POST /conversations/{uuid}/turn` with the retrieval config given on the
   command line, three repetitions, and the stored assistant message is graded. Box
   scoring is offline (no stack needed).
8. **Initial scope**: three tenders, chosen for kind coverage: `NOO-2026-0304_10BW62-1`
   (HVA, flattened), the WNA Berlin tender (WSV, XFA), and one VHB tender from the corpus
   (filename `FB 211, 212, 214, 213, 233.pdf` or a VHB 211 single). Vergabestelle forms
   only (role from `classify_form_role`, plus any `UNBEKANNT` form Arthur picks).

## Label schema

`eval/forms/labels/<tender>/<pdf-stem>.json`:

```json
{
  "tender": "NOO-2026-0304_10BW62-1",
  "pdf": "Heftung 1 Angebotsaufforderung/HVA_B_StB_111_Vorlage_Aufforderung_zur_Angebotsabgabe.pdf",
  "form_id": "HVA B-StB 111",
  "kind": "flattened",
  "labelled_pages": [1, 2, 3],
  "lines": [
    {"page": 3, "bbox": [105.0, 482.0, 468.0, 492.0],
     "text": "Nebenangebote sind nicht zugelassen; Nr. 4 der Teilnahmebedingungen gilt nicht.",
     "state": "checked"},
    {"page": 3, "bbox": [105.0, 509.0, 505.0, 519.0],
     "text": "Nebenangebote sind zugelassen (s. auch Nr. 4 der Teilnahmebedingungen) - ausgenommen",
     "state": "unchecked"}
  ]
}
```

Only lines with state `unchecked` or `checked` are written; `none` is implicit. `kind`
is `detect_form_kind` at label time (`xfa`, `acroform`, or `flattened` for zero-field
PDFs, decided in the tool by the task-08 rule: zero fields and a form id).

`eval/forms/facts/<tender>.json`:

```json
{
  "tender": "NOO-2026-0304_10BW62-1",
  "facts": [
    {"key": "nebenangebote_zugelassen",
     "question": "Sind Nebenangebote für dieses Projekt zugelassen?",
     "kind": "yes_no", "gold": "nein",
     "source": {"pdf": "Heftung 1 Angebotsaufforderung/HVA_B_StB_111_....pdf", "page": 3, "section": "6 Nebenangebote"}}
  ]
}
```

Fact templates offered by the tool (the labeler fills `gold` and `source`, deletes what a
tender does not have, adds free rows):

| key | question | kind | usual form |
|---|---|---|---|
| `nebenangebote_zugelassen` | Sind Nebenangebote zugelassen? | yes_no | 111 § 6 |
| `losweise_vergabe` | Erfolgt die Vergabe losweise? | yes_no | 111 § 4 |
| `mehrere_hauptangebote` | Sind mehrere Hauptangebote zugelassen? | yes_no | 111 § 5 |
| `nachforderung` | Werden fehlende Unterlagen nachgefordert? | yes_no | 111 § 3.3 |
| `kommunikation_elektronisch` | Erfolgt die Kommunikation elektronisch über die Vergabeplattform? | yes_no | 111 |
| `angebotsform` | In welcher Form ist das Angebot einzureichen? | list | 111 |
| `zuschlagskriterien` | Welche Zuschlagskriterien gelten? | list | 111 § 7 |
| `zuschlagsfrist` | Wann endet die Zuschlags-/Bindefrist? | value | 111 / 312-B |
| `ausfuehrungsbeginn` | Wann ist mit der Ausführung zu beginnen? | value | 131 § 1 |
| `fertigstellung` | Bis wann ist die Leistung fertigzustellen? | value | 131 § 1 |
| `vertragsstrafe` | Ist eine Vertragsstrafe vereinbart? | yes_no | 131 |
| `sicherheit_vertragserfuellung` | Wie hoch ist die Sicherheit für die Vertragserfüllung? | value | 131 |
| `sicherheit_maengel` | Wie hoch ist die Sicherheit für Mängelansprüche? | value | 131 |
| `stoffpreisgleitklausel` | Gilt eine Stoffpreisgleitklausel? | yes_no | 131 / 132 |
| `unterlagen_mit_angebot` | Welche Unterlagen sind mit dem Angebot einzureichen? | list | 109 / 317-B |

## Changes

### 1. Dependency group and layout

- `pyproject.toml`: `[dependency-groups] tools = ["streamlit>=1.40"]` (keep `dev` as is).
  `uv lock` is updated; `DEVOPS.md` gets the run command.
- `server/scripts/form_labeler/`: `app.py` (Streamlit entry), `corpus.py` (tender and
  PDF discovery, role, kind), `pages.py` (page rendering and caching), `proposals.py`
  (the geometric aid, decision 4), `store.py` (read/write the JSON files, atomic write),
  `facts.py` (templates and the facts editor). All pure except `app.py`; `store.py` and
  `corpus.py` are unit-tested.
- `eval/forms/labels/`, `eval/forms/facts/`, `eval/forms/README.md` (schema, how to run
  the tool and the script, what the numbers mean).
- `.gitignore`: `eval/forms/.cache/` (rendered pages).

### 2. Corpus discovery (`corpus.py`)

- `list_tenders(root) -> list[Tender]` from the directories of `server/training`
  (ZIP-extracted folders; skip the `.json` and `.zip` siblings).
- `list_forms(tender) -> list[FormPdf]`: every PDF under the tender dir with
  `kind = detect_form_kind(bytes)` or, for zero fields, "flattened" when
  `classify_form_role(name)` returns a `form_id` (task 08's rule, applied here from the
  filename only; the footer rule arrives with 08 and the tool is updated then). Carry
  `role`, `form_id`, page count (pdfplumber as in `project_service`). Vergabestelle and
  `UNBEKANNT` first, Bieter forms last and collapsed.
- `page_lines(pdf_bytes, page) -> list[NewSourceLine]` via `extract_source_lines`, cached
  per PDF in session state.

### 3. Page rendering (`pages.py`)

- `render_page(pdf_path, page, dpi=110) -> Path` with `pdf2image.convert_from_path(...,
  first_page=page, last_page=page)`, cached as PNG under `eval/forms/.cache/<sha1 of
  path>/<page>.png`. Same renderer as the production thumbnails.

### 4. The app (`app.py`)

- Sidebar: tender select; form list as keyed `st.button`s (the pattern from the LV
  matching tool: `st.container(height=...)`, primary style on the selected row, a
  `:material/check_circle:` icon on fully labelled forms); page nav (`Seite n / N`) with
  "nächste unbestätigte Seite".
- Main, two columns: left the page image; right one row per extracted line of the page:
  the line text (monospace, full width, marginal-token lines like "X" or "6.1" shown
  dimmed) and a horizontal `st.radio` with options `–`, `☐`, `☒` (values `none`,
  `unchecked`, `checked`). Proposed values are rendered with a coloured caption
  "Vorschlag" until the page is confirmed.
- Buttons: "Seite bestätigen" (writes the file, marks the page labelled, advances to the
  next unconfirmed page of the form, wrapping to the next form when done), "Vorschläge
  verwerfen" (all lines of the page back to `none`), "Vorschläge neu" (re-run
  `proposals.py` for the page).
- Facts tab per tender: `st.data_editor` over the fact rows (`key`, `question`, `kind`,
  `gold`, `source.pdf`, `source.page`, `source.section`), pre-filled from the templates
  on first open, "Speichern" writes `facts/<tender>.json`. Deleting a row removes the
  fact; `gold` empty means "not yet labelled" and the script skips it.
- Status line: labelled pages / total pages for the tender; facts with gold / total.

### 5. Proposals (`proposals.py`)

- `propose(pdf_path, page, lines) -> dict[int, State]` keyed by line index: squares from
  pdfplumber (`rects` with side 6-12pt, and squares assembled from `lines`), tick glyphs
  (`xX×✓✔`) inside a square, nearest line to the right within 4pt vertically and 14pt
  horizontally. Returns `checked`/`unchecked` for matched lines only. About 40 lines; it
  is deliberately not imported from `shared/` and 08 does not import it.

### 6. Store (`store.py`)

- `load_labels(path) -> FormLabels`, `save_labels(path, labels)` with a temp file and
  rename; Pydantic models `FormLabels`, `LineLabel`, `FactFile`, `Fact`, `FactSource`,
  `extra="forbid"`. The models live in the tool, not in `shared/models` (nothing in the
  product reads them).

### 7. Measurement script (`server/scripts/eval_form_labels.py`)

- `--boxes`: for every label file, run a detector given by `--detector
  module:function` (default `shared.services.ingestion.forms.flattened:find_toggles`
  once 08 exists; before that, `--detector none` prints label statistics only) and the
  attachment step on the PDF; match detector lines to labels (decision 2); print per form
  family and overall: labelled boxes, detected boxes, true/false positives, misses,
  precision, recall, and a list of every miss and false positive with tender, pdf, page,
  text. Offline.
- `--facts`: for every facts file, resolve the tender to a project on the running stack
  (`GET /projects`, match `vergabe_id` or `project_name` against the tender folder name;
  `--project-map tender=uuid` to override), create one conversation per repetition with
  title `form-eval-<tender>-<n>`, send each question with the retrieval config from
  `--modality plus --bm25 [--multi-query] [--cross-encoder]`, read the stored assistant
  message, grade: `yes_no` by the first `ja`/`nein` token in the answer after
  normalisation (`Ja.`, `Nein,`, `Ja, aber` -> `ja`), `value` and `list` by
  case-insensitive containment of every gold string in the answer. Print per tender and
  overall: facts, correct in n/n runs, correct in some runs, wrong; and the full answer
  text for every fact that was not correct in all runs. `--delete-conversations` removes
  the probe conversations afterwards (default keeps them for inspection).
- Exit code 0 always; this is a report, not a test. Defaults for `--api
  http://localhost:8000` and `--repeat 3`.

### 8. Tests

- `tests/unit/scripts/test_form_labeler_store.py`: round trip, `extra="forbid"`
  rejects an unknown key, atomic write leaves no temp file.
- `tests/unit/scripts/test_form_labeler_corpus.py`: `list_forms` ordering and the
  flattened rule on a pypdf-built zero-field PDF named `HVA_B_StB_111_x.pdf` versus
  `Plan_1.pdf`.
- `tests/unit/scripts/test_eval_form_labels.py`: line matching by bbox overlap and text
  containment (merged line matches the original label line; a different line does not);
  the `yes_no` grader on `Ja.`, `Nein, ...`, `Ja, aber nur eingeschränkt`.
- The Streamlit app itself is checked by hand (and optionally headlessly with
  playwright-core as the LV matching tool was).

## Done means

- `uv run --group tools streamlit run server/scripts/form_labeler/app.py` opens, lists the
  three tenders, renders pages, writes label files.
- `eval/forms/labels/` holds every Vergabestelle form of the three tenders with all pages
  confirmed; `eval/forms/facts/` holds at least 12 facts with gold per tender.
- `uv run python -m scripts.eval_form_labels --boxes --detector none` prints the label
  statistics; `--facts --modality plus --bm25` against the dev stack prints the baseline
  table. Both outputs go into the task report as the pre-08 baseline. The expectation
  from the probes of 2026-10-11 is that `nebenangebote_zugelassen` on NOO-2026-0304 is
  not correct in 3 of 3 runs.
- `uv run pytest tests/unit/scripts -q` green; ruff clean on touched files; `uv lock`
  updated; `DEVOPS.md` and `eval/forms/README.md` written.
- Label files are left uncommitted in the working tree for Arthur to review and commit.
