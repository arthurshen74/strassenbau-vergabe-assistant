# Task 08: One form model for XFA, AcroForm and flattened Formblätter; chunks carry only what is checked

Depends on: 07 (form documents) merged on main (`b2969f1`). Task 09 (ground-truth labeler)
is not a build dependency, but the measurement in "Done means" uses its labels and its
script, so 09 should be finished or running when this task reaches that step.

## Use a worktree

Preflight, on `main` before creating the worktree:

```bash
test -f sql/24_form_documents.sql && test -d server/shared/services/ingestion/forms
```

```bash
git worktree add ../swa-task08 -b task/08-form-flattening
```

Follow the "Worktree setup" section of `tasks/README.md` (own `uv sync` / `npm ci`, test DB
`POSTGRES_DB=roadbuilders_t08`, never touch the compose stack, no commits). This task has
**no schema change and no migration**; `sql/25` stays free.

## Goal

The forms that carry a tender's decisions (HVA B-StB 101, 109, 111, 131, 132, 144 and the
EU variants) arrive as *flattened* PDFs: zero AcroForm fields, the checkbox is a drawn
square and the tick is a text glyph. Task 07 correctly leaves them on the prose path, where
`pdftotext` emits the tick as a line of its own ("6.1 / X / 6.2 / label A / label B") and
an empty box leaves no trace at all. The retrieval chunk then contains every template
option, and the answer model guesses. After this task:

- a flattened PDF whose Formblatt id is known becomes a `FORM_DOCUMENT` like a fillable one;
- all three form kinds produce the **same SourceLine contract**: an option line carries a
  checked/unchecked marker in front of its printed text, a filled text field is
  `label: value`, headings and static prose are untouched;
- `chunk_form` builds one chunk per form section containing **only checked options,
  filled fields, headings and static prose**. Unchecked options and everything nested
  under them never reach a chunk. They stay in `source_lines` and `form_fields` and are
  visible on the thumbnail and in the Felder tab;
- the Formblatt id is read from the page footer when the form prints one, and from the
  filename otherwise; a Bieter form is skipped **only** when the id comes from the
  Formblatt table, never from a title keyword alone.

## Evidence this is built on (2026-10-11)

- **Corpus** (`server/training`, 198 PDFs whose name carries a form token or form word):
  110 flattened, 76 AcroForm, 12 XFA. Every Vergabestelle HVA form is flattened in every
  project; the AcroForms are almost all Bieter forms (103, 106, 107, 121, VHB 221/222),
  which upload classification already marks `skipped`. The current FORM path therefore
  mostly handles forms that are never ingested.
- **HVA_B_StB_111 of NOO-2026-0304** (5 pages, 0 fields): 29 tick glyphs ("X",
  LiberationSans 8pt), 24 of them emitted by `pdftotext -bbox-layout` as a standalone
  block because the section-number column ("6.1", "6.2") interleaves; 5 happened to merge
  ("X nicht zugelassen."). Boxes are four vector line segments of 9-10pt (pdfplumber:
  69 `lines`, 1 `rect`, 0 `curves` on page 3). HVA 131/132 use "×" instead of "X".
- **Geometry works**: on page 3 pdfplumber finds all 17 squares; each of the 4 glyphs falls
  inside exactly one; the label line to the right (same `yMin` within 3pt, `x0` within
  14pt of the box's right edge) resolves correctly for every box.
- **The RAG answer is wrong today**: "Sind Nebenangebote für dieses Projekt zugelassen?"
  on NOO-2026-0304 answered "Ja" (retrieval_debug, plus+bm25), "Nein" (chat API,
  plus+bm25, citing the Baubeschreibung) and "Ja, aber nur eingeschränkt" (chat API, full
  pipeline, claiming the zugelassen option was "angekreuzt"). The form page says 6.1
  "nicht zugelassen" is checked. Probe conversations `nebenangebote-probe-*` are on the
  dev DB.
- **Footer ids**: every HVA form prints `NNN HVA B-StB <Titel> MM-YY` in the footer of
  every page (`101 HVA B-StB Vordruck Teilnahmebedingungen National 03-23`,
  `111 HVA B-StB Vorlage Aufforderung zur Angebotsabgabe NTVergG 02-24`, `104.1 HVA B-StB
  Eignungsleihe ...`). On the corpus the footer agrees with the filename token in all 27
  HVA files that have both and adds an id to 24 files without a token (`00 - Aufforderung
  zur Angebotsabgabe.pdf` -> 111, `C01 - Angebotsschreiben.pdf` -> 121, `109 HVA-B
  Vorlage ...` -> 109, `301-Angebotsschreiben NTVergG` -> 121). WSV forms print no number
  (metadata only, task 07). The VHB footer (`VHB - Bund - Ausgabe 2017 ...`) was not
  matched reliably in the scan; VHB stays filename-based until a verified pattern exists.
- **Keyword false positives** (role from `BIETER_KEYWORDS` alone): `Erläuterung zum
  Teilnahmeantrag.pdf`, `Erläuterungen zur Eigenerklärung kommunale und sonstige AG.pdf`
  are Vergabestelle explanations; `Anlage_Einzelnachweise_TK_FRS_....pdf` is unclear. A
  keyword is a hint, not a certainty.

## Decisions already made (do not re-litigate)

1. **Unchecked options never reach a chunk** (Arthur, 2026-10-11). Not with a marker, not
   as "nein". They are preserved in `source_lines` (full page text) and `form_fields`
   (value `nein`), and visible on the thumbnail. A section in which nothing is checked
   gets one line `keine Option angekreuzt` so "nicht angegeben" is distinguishable from
   "Abschnitt fehlt".
2. **One SourceLine contract for every form kind.** An option line is the printed label
   text prefixed by `OPTION_CHECKED_PREFIX = "[x] "` or `OPTION_UNCHECKED_PREFIX = "[ ] "`.
   A text or choice field is `label: value` as today. Headings are `## <section>` as
   today. Static prose is untouched. These are contract literals in `forms/model.py`,
   referenced by the extractors, `chunk_form` and nothing else (the UI reads
   `form_fields`, not line text).
3. **Toggle state is attached by geometry, once, for AcroForm and flattened alike.** A
   `Toggle(page, bbox, checked)` is produced by the kind-specific reader (widget `/Rect`
   plus `/V`/`/AS` for AcroForm; vector square plus glyph test for flattened) and a single
   `attach_toggles` function prefixes the marker onto the printed line to the right of the
   box. The AcroForm `label: ja/nein` lines from task 07 go away where a printed line is
   found; the `/TU` fallback line (`[x] <tooltip>`) stays for widgets with no printed
   label nearby. XFA has no geometry: a `checkButton` field becomes `[x] caption` /
   `[ ] caption` directly; an `exclGroup` (radio) stays `caption: <selected option>`.
4. **Flattened detection is id-based, not geometry-based.** A zero-field PDF is
   `FORM_DOCUMENT` with `FormKind.FLATTENED` iff `identify_formblatt` returns a row of the
   Formblatt table (footer first, filename token second). No table row -> prose, exactly
   as today. Keyword-only files (no footer, no token) stay prose: without an id we are not
   certain it is a form, and prose extraction is today's behaviour. Scanned forms without
   a text layer stay prose.
5. **Identification order: footer, filename token, title keyword.** `form_id` is set only
   by footer or token. The footer wins over a conflicting filename token (the footer is
   printed by the issuing authority; the filename is the tender's own ordering).
6. **Skip rule: `role is BIETER and form_id is not None`.** This replaces decision 4 of
   task 07. A keyword-only Bieter form is stored with role `BIETER` (badge in the UI) but
   enqueued `queued` and ingested. With decision 1 an ingested blank Bieter form yields
   its static prose and pre-filled Kopf, which is harmless; a wrongly skipped Vergabestelle
   explanation sheet is a lost document.
7. **Chunk per form section, section from the text.** A heading is a line matching
   `^\d+\s+\S` whose number has no dot (`6 Nebenangebote`, `7 Angebotswertung:`), after the
   number column has been re-attached (see `merge_marginal_tokens`). Sub-numbers (`3.3`,
   `6.1`) are content lines. The same rule runs for AcroForm pages; `## Seite n` remains
   the fallback when a page has no numbered heading. XFA keeps its subform sections.
8. **Drop rule in `chunk_form`**: an unchecked option line is dropped together with every
   following line whose `bbox.x0` is greater than the option's `x0`, until a line with
   `x0 <= option.x0` or a heading. For XFA (no geometry) only the unchecked line itself is
   dropped. The marker prefix is stripped from checked lines in the chunk text; the chunk
   reads as plain statements under the section heading.
9. **No VLM, no OCR.** Geometry only. A box that cannot be resolved to a label line is
   counted and logged once per document (`n unresolved boxes`) and left unmarked; the
   page text is then as it is today.
10. **Chunk size cap stays.** `CHUNK_SIZE` continuation with repeated heading as in task 07.
11. **Re-ingest, no migration.** The chunk shape changes, so already-ingested forms are
    re-ingested by hand (archive index handles replacement). `form_fields` rows for a
    flattened form are new data in an existing table.

## Current state (read before changing)

- `server/shared/services/ingestion/extraction.py`: `extract_source_lines` /
  `parse_bbox_layout` (poppler `pdftotext -bbox-layout`, one `NewSourceLine` per `<line>`,
  top-origin bbox in points). Both pdfplumber and pdftotext use the same frame; no
  transformation is needed between them (verified: glyph at y=484 from pdftotext, box
  y=484-494 from pdfplumber).
- `server/shared/services/ingestion/forms/`: `detect.py` (`FormKind {XFA, ACROFORM}`,
  `detect_form_kind(pdf_bytes)`), `role.py` (`FORMBLAETTER` table, `_find_token`,
  `classify_form_role(file_name)`), `model.py` (`FORM_SECTION_PREFIX`, `CHECKED`,
  `UNCHECKED`, `FormExtraction`, `field_line`, `section_heading`), `acroform.py`
  (`extract_acroform`, `_merge_lines` appends `label: ja/nein` lines per page from `/TU`),
  `xfa.py` (`extract_xfa`, checkbox -> `caption: ja/nein`), `extraction.py`
  (`extract_form(pdf_bytes, document_uuid, kind)`).
- `server/shared/services/ingestion/chunking.py:85` `chunk_form`: splits on
  `FORM_SECTION_PREFIX` lines, never mid-line, caps at `CHUNK_SIZE`, no drop logic.
- `server/shared/services/ingestion/ingestion_service.py:132` dispatch on
  `document_type`; `:285-330` `_ingest_form_document` (detect -> extract -> persist lines
  and fields -> `chunk_form` -> `_embed_and_index(..., SourceDocType.FORM)`).
- `server/shared/services/project_service.py:358` `classify_document(file_name, data)`:
  `detect_form_kind(data) is not None` -> `FORM_DOCUMENT` with
  `classify_form_role(file_name)`; `:348` enqueues `SKIPPED` when role is `BIETER`.
- `server/shared/models/form_field.py`: `section, name, label, value, page`; repository
  `form_fields`; API `GET .../documents/{uuid}/form-fields`; UI `FormFieldsTable.tsx`,
  `DocumentDetailDialog.tsx` (Felder tab), `ProjectDetails.tsx` (type badge, role line).
- `pdfplumber` is a declared dependency, used in `project_service.py:504` for page counts.
  `pdf2image` renders thumbnails. `pypdf==6.12.2` reads AcroForms.
- Tests: `tests/unit/services/ingestion/forms/test_acroform.py` (2), `test_xfa.py`,
  `tests/integration/services/test_form_corpus.py` (asserts 80 AcroForm, 12 XFA, 3
  `UNBEKANNT`), `tests/form_pdfs.py` (pypdf fixture builder for AcroForms).
- `tests/integration/services/test_form_corpus.py` is the regression guard for the
  "AcroForm dict with zero fields" trap; its counts change in this task.

## Changes

### 1. Contract literals and models (`forms/model.py`, `shared/models`)

- `OPTION_CHECKED_PREFIX = "[x] "`, `OPTION_UNCHECKED_PREFIX = "[ ] "`,
  `NO_OPTION_CHECKED = "keine Option angekreuzt"`, `option_line(label, checked) -> str`.
  `CHECKED`/`UNCHECKED` (`ja`/`nein`) remain the `form_fields.value` vocabulary.
- `Toggle(BaseModel)`: `page: int`, `bbox: tuple[float, float, float, float]` (top-origin),
  `checked: bool`, `label: str | None` (the `/TU` or XFA caption, used only as fallback).
- `FormExtraction` unchanged (`lines`, `fields`). `FormKind` gains `FLATTENED = "flattened"`.
- No change to `FormField`, `Document`, `DocumentRead`.

### 2. Identification (`forms/identify.py`, `forms/role.py`)

- `forms/identify.py`: `FOOTER_HVA = re.compile(r"^\s*(\d{3}(?:\.\d)?)\s+HVA\s*B-StB\b",
  re.M | re.I)`; `identify_from_text(text) -> tuple[FormFamily, str] | None` on the
  `pdftotext` text of the first two pages (`-f 1 -l 2`, plain layout; one subprocess,
  milliseconds). `104.1` maps to table number `104` (variant digit is not part of the
  key, same as `104_2` today). Only the HVA pattern ships; add a VHB or WSV pattern only
  with a corpus check like the one in "Evidence".
- `role.py`: `classify_form_role(file_name, content_id: tuple[FormFamily, str] | None =
  None) -> tuple[FormRole, str | None]`: content id first, then filename token, then
  keyword. `form_id` is rendered from whichever id matched.
- Add to `FORMBLAETTER` the rows observed only through footers: HVA `113 Gewichtung
  Zuschlagskriterien` (V). Every added row must be observed in the corpus.

### 3. Detection (`forms/detect.py`, `project_service.py`)

- `detect_form_kind(pdf_bytes, file_name) -> FormKind | None`: XFA and AcroForm as today;
  else `FLATTENED` when `identify_from_text` or `_find_token(file_name)` hits a table row;
  else `None`.
- `classify_document(file_name, data)`: unchanged signature, passes `file_name` through,
  computes the content id once and hands it to `classify_form_role`. Skip rule per
  decision 6: `status = SKIPPED if role is BIETER and form_id is not None else QUEUED`.
  Update the docstring.

### 4. Toggle attachment (`forms/toggles.py`)

- `TOGGLE_Y_TOLERANCE = 4.0`, `TOGGLE_X_GAP = 14.0`, `MARGINAL_TOKEN = re.compile(r"^(?:[xX×✓✔]|\d+(?:\.\d+)*)$")`.
- `merge_marginal_tokens(lines) -> list[NewSourceLine]`: a line whose text is a single
  marginal token (tick glyph or section number) is merged into the nearest line on the
  same page whose `yMin` is within `TOGGLE_Y_TOLERANCE` and whose `x0` is to the right:
  a number is prefixed (`6.1 Nebenangebote sind nicht zugelassen; ...`), a tick glyph is
  dropped (its state comes from the toggle, not the glyph). No partner -> the line is
  kept as is. The merged line keeps the partner's bbox extended to the token's `x0`.
- `attach_toggles(lines, toggles) -> tuple[list[NewSourceLine], int]`: for each toggle
  find the line on the same page with `yMin` within tolerance and `x0` in
  `[bbox.x1, bbox.x1 + TOGGLE_X_GAP]`; prefix `option_line`. A toggle with no partner but
  with a `label` emits a fallback line `option_line(label, checked)` at the toggle's
  position; a toggle with neither is counted as unresolved. Returns the new lines (line
  ids renumbered in page, y, x order) and the unresolved count.
- Pure functions over `NewSourceLine`; no I/O; `bbox` is the only geometry used.

### 5. Flattened reader (`forms/flattened.py`)

- `extract_flattened(pdf_bytes, document_uuid) -> FormExtraction`:
  1. `lines = extract_source_lines(pdf_bytes, document_uuid)`.
  2. `toggles = find_boxes(pdf_bytes)`: with pdfplumber per page, squares from `rects`
     with side `BOX_MIN_SIDE = 6.0` to `BOX_MAX_SIDE = 12.0`, plus squares assembled from
     `lines` (a horizontal pair with equal `x0`/`x1` and a vertical gap in the same range).
     Checked iff a char with `text in TICK_GLYPHS = frozenset("xX×✓✔")` or a ZapfDingbats
     /Wingdings char has its centre inside the square (1pt slack). Box glyph fonts
     (`ZapfDingbats` box characters) count as a box without vector lines.
  3. `lines = merge_marginal_tokens(lines)`; `lines, unresolved = attach_toggles(lines,
     toggles)`; insert `## <heading>` lines per decision 7 (a `## Seite n` fallback per
     page without a heading).
  4. `fields`: one `NewFormField` per toggle (`section` = current heading, `name` =
     `f"p{page}-{index}"`, `label` = the attached line's text without marker, `value` =
     `ja`/`nein`, `page`). No text-field rows: a flattened form's filled values are plain
     printed text and stay prose lines.
- `extract_form` dispatches `FLATTENED` here. Log once per document: `form (flattened):
  n boxes, m checked, k unresolved, s sections`.

### 6. AcroForm and XFA readers on the shared contract

- `acroform.py`: build `Toggle`s from checkbox/radio widgets (`/Rect` converted to
  top-origin as today, `checked` from `/AS`/`/V`, `label` = `/TU`), then
  `merge_marginal_tokens` + `attach_toggles` + headings exactly as the flattened reader.
  `_merge_lines` and its appended `label: ja/nein` lines are removed. `fields` rows are
  unchanged (the UI depends on them).
- `xfa.py`: a `checkButton` emits `option_line(caption, checked)` instead of
  `field_line(caption, ja|nein)`; `fields` rows unchanged. Lines keep `bbox = (0,0,0,0)`.
- Factor the shared tail (`merge_marginal_tokens`, `attach_toggles`, headings) into one
  function in `toggles.py` used by both geometric readers; this is the third instance of
  the same sequence, so the extraction is justified.

### 7. Chunking (`chunking.py`)

- `chunk_form`: as today for grouping and the size cap, plus the drop rule (decision 8):
  track `dropping_below_x0: float | None`; an `OPTION_UNCHECKED_PREFIX` line sets it to the
  line's `bbox[0]` (or drops only itself when the bbox is all zero); subsequent lines with
  `bbox[0] > dropping_below_x0` are skipped; a line with `bbox[0] <= dropping_below_x0` or
  a heading clears it. Checked lines are emitted without the prefix. A section whose
  content would be empty after dropping gets the single line `NO_OPTION_CHECKED`.
- `source_doc_pages` from the emitted lines only.

### 8. Worker and service wiring

- `ingestion_service.py`: `detect_form_kind(pdf_bytes, document.file_name)`; the activity
  line shows the kind and, for flattened/AcroForm, the toggle counts from the reader
  (return them on `FormExtraction` as `toggles: int`, `checked: int`, `unresolved: int`,
  defaults 0 for XFA). `NotAFormError` stays for a `FORM_DOCUMENT` whose bytes no longer
  detect.
- `IngestionResult` / `ingestion_cost`: unchanged.

### 9. UI

- Nothing structural. Flattened forms get the indigo `FORM` badge, `form_id` and role line
  automatically. `FormFieldsTable` shows the toggle rows (`label | ja/nein | page`). The
  Chunks tab shows the collapsed chunks. Check `DocumentDetailDialog` opens on the Felder
  tab for flattened forms as it does for other forms.
- `npm run gen:types` only if a DTO changed (none expected).

### 10. Documentation

- `AI_ARCHITECTURE.md`: the three form kinds, the shared toggle attachment, the chunk
  collapse rule, that forms are never read by a VLM.
- `APPLICATION_ARCHITECTURE.md`: `FormKind.FLATTENED`, the footer-based `form_id`, the
  skip rule.
- `GLOSSARY.md`: "flattened Formblatt", "Toggle".
- `extraction.py` docstring: note that the flattened-form path re-attaches tick glyphs
  and section numbers that `pdftotext` emits as separate blocks.
- `tasks/07-form-documents.md` "Known limitations": strike the last bullet.

### 11. Tests

Fixture builder (`tests/form_pdfs.py`, extend): `flattened_pdf(boxes, texts)` writes a
one-page PDF with a hand-built content stream (Helvetica base font, no embedding): `re`
rectangles for boxes, `Tj` text for labels, an `X` glyph inside checked boxes, and
numbered headings. pypdf's `PdfWriter` can add the page with a `DecodedStreamObject`
content stream and a `/Font` resource. Do not copy training PDFs into the repo.

Unit (`tests/unit/services/ingestion/forms/`):
- `test_identify.py`: HVA footer lines (`111 ... 03-23`, `104.1 ...`, NTVergG variant)
  resolve; a Baubeschreibung page does not; footer beats filename token.
- `test_role.py` (extend): content id first; keyword-only -> `(BIETER, None)`.
- `test_detect.py` (extend): zero fields + HVA footer -> `FLATTENED`; zero fields + no id
  -> `None`; AcroForm with footer -> `ACROFORM`.
- `test_toggles.py`: `merge_marginal_tokens` (number prefixed, glyph dropped, no partner
  kept); `attach_toggles` (partner found, fallback label, unresolved count, y tolerance
  boundary, two boxes in one row with the HVA 4-column layout from page 4:
  `X in Textform, | X mit fortgeschrittener/m ... | X mit qualifizierter/m ...`).
- `test_flattened.py`: the fixture with a checked and an unchecked box, a nested
  sub-option, a heading -> expected lines and `form_fields` rows.
- `test_acroform.py` (rewrite the two tests): widgets attach to printed lines; `/TU`
  fallback when there is no printed line; pushbutton excluded.
- `test_xfa.py` (extend): checkbox becomes an option line; radio stays a field line.
- `test_chunking.py` (extend): drop rule with nesting, heading clears the drop, empty
  section -> `NO_OPTION_CHECKED`, prefix stripped, XFA zero-bbox drops only itself.
- `test_project_service.py` (extend): skip only with `form_id`; keyword-only Bieter
  enqueued `queued`.

Integration:
- `ingest_document` on a flattened fixture `FORM_DOCUMENT` with mocked embeddings:
  `FORM` chunks, no unchecked text in any chunk, `form_fields` rows present.
- `test_form_corpus.py`: update the expected counts (compute them in the worktree; expect
  AcroForm 80, XFA 12, flattened about 60, and list the `UNBEKANNT` names) and add: every
  HVA PDF whose footer says `111` classifies as `FORM_DOCUMENT` with `form_id`
  `HVA B-StB 111`; no `LV Los*.pdf` and no Baubeschreibung is a form.

### 12. Measurement (uses task 09)

- Run `uv run python -m scripts.eval_form_labels --boxes` in the worktree: box-level
  precision and recall of `find_boxes` + `attach_toggles` against the labels in
  `eval/forms/labels/`. Target: precision >= 0.98, recall >= 0.95 per form family.
- Re-ingest NOO-2026-0304 on the dev stack, then `--facts` against the running API with
  `plus + bm25`, three repetitions. Target: every yes/no fact correct in 3 of 3 runs;
  report the value facts in the task report.
- Before the change, run the same two commands and keep the output in the task report as
  the baseline.

## Known limitations (state them in the docs, do not fix here)

- VHB and WSV forms get no footer id; their `form_id` still depends on the filename.
- Keyword-only forms (no footer, no token) stay prose.
- Scanned forms without a text layer stay prose.
- XFA lines have no geometry, so nesting under an unchecked option is not applied there;
  only the unchecked line itself is dropped.
- Hand-drawn ticks and filled squares without a glyph are not detected; the box is
  reported as unchecked. The unresolved/checked counts in the activity log are the signal.
- Bundles (`FB 211, 212, 214, 213, 233.pdf`) are still not split.

## Done means

- `uv run pytest` green; `uvx ruff check` / `format` clean on touched files only.
- `cd ui && npx tsc --noEmit -p tsconfig.app.json` green (no UI edits expected).
- Baseline and after-change output of `scripts/eval_form_labels` in the task report, with
  the targets in section 12 met.
- Manual on the dev stack after re-ingesting NOO-2026-0304: `HVA_B_StB_111_...pdf` is
  `FORM_DOCUMENT`, `form_id` `HVA B-StB 111`, role Vergabestelle, status `done`; its
  section 6 chunk reads `## 6 Nebenangebote` followed by `6.1 Nebenangebote sind nicht
  zugelassen; Nr. 4 der Teilnahmebedingungen gilt nicht.` and nothing else; the Felder tab
  lists the 17 page-3 toggles with 4 `ja`; the chat answers "Nein" to the Nebenangebote
  question with `plus + bm25`; `Nachweis für Sicherungsarbeiten an Arbeitsstellen.pdf`
  (keyword-only) is `queued`/`done`, not `skipped`; the AcroForm Bieter forms 103, 106,
  107, 121 remain `skipped`.
- Create a project from the WNA Berlin ZIP (XFA) and confirm the task 07 Felder
  expectations still hold and FB 312-B's chunks contain no `[ ]` text.
