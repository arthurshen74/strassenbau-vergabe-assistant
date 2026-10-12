# Task 07: Form documents (Formblätter) as their own document type

Depends on: 06 (live ingest console) merged on main, so `sql/24` is the next free migration
number and `ConsoleJobRead` / the console stream exist.

## Use a worktree

Preflight, on `main` before creating the worktree:

```bash
test -f sql/23_project_info_activity_log.sql && grep -q "class ConsoleJobKind" server/shared/models/enums.py
```

```bash
git worktree add ../swa-task07 -b task/07-form-documents
```

Follow the "Worktree setup" section of `tasks/README.md` (own `uv sync` / `npm ci`, test DB
`POSTGRES_DB=roadbuilders_t07`, never touch the compose stack, migrations on a scratch DB,
no commits).

## Goal

A tender ZIP contains fillable PDF forms (VHB, HVA B-StB and WSV Formblätter). Today every
PDF is classified `PROSE_DOCUMENT` by its suffix and goes through `pdftotext`. For dynamic
XFA forms that yields one junk chunk ("Please wait... upgrade Adobe Reader") and nothing
else; for AcroForms it yields flattened text with no label/value structure and no checkbox
state. After this task:

- a fillable form becomes a `FORM_DOCUMENT`, detected from the bytes, not the filename;
- its role is derived from the filename: issued by the Vergabestelle, to be filled by the
  Bieter, or unknown;
- Bieter forms are stored but not ingested (job status `skipped`, re-ingestable by hand);
- Vergabestelle and unknown forms are extracted field by field (XFA from the embedded XML,
  AcroForm from the field dictionary), persisted as source lines plus a structured
  `form_fields` table, chunked per form section, and indexed as `SourceDocType.FORM`;
- the LangChain pass is not run for forms;
- the UI shows the type, the Formblatt id, the role, the skipped state, and a key/value
  tab in the document detail dialog.

## Evidence this is built on (training corpus, 980 PDFs, 2026-10-10)

- `pdfinfo` says `Form: AcroForm` for 221 files, but 140 of them have **zero fields**
  (plans, Gutachten, `LV Los 1-3.pdf`, flattened Formblätter). They are prose and already
  extract fine. "Has an `/AcroForm` dict" is not "is a form"; the field count is.
- 92 real fillable forms: 80 AcroForm with >= 3 fields, 12 XFA (all in the WNA Berlin
  tender, every one of them currently extracted as the placeholder text).
- Blank forms essentially do not exist (1 of 92). Bieter forms carry a Kopf pre-filled by
  the Vergabestelle (4-10 of 24-85 fields) and an empty body; Vergabestelle forms range
  from 3/3 to 55/109 filled. **No fill-ratio threshold separates them**; the Formblatt
  identity does.
- The Formblatt number is in the filename for 76 of 92 (`HVA_B_StB_121_...`, `VHB_221_...`,
  `T1.1 FB 312-B ...`, `EFB-Preis ...`). It is in PDF metadata only for the WSV XFA files
  and in the first-page text for none of the HVA forms. The 16 without a token are all
  recognisable by a title word (Angebotsschreiben, Eigenerklärung, Eignungsleihe, ...)
  except three Vergabestelle documents, which is why unknown is ingested, not skipped.
- `pdftotext -bbox-layout` renders AcroForm text-field appearances (the docstring in
  `extraction.py` is right) but not checkbox state in a usable form, and not XFA at all.
- The LangChain index is read only by the document-detail chunk viewer
  (`document_detail.py:59,85`); the `LANGCHAIN` retrieval modality was removed in
  `7ecc888`. It stays as is for prose; forms skip it.

## Decisions already made (do not re-litigate)

1. **`DocumentType.FORM_DOCUMENT` is a third, user-visible type.** Not an internal
   extraction switch. The UI mirrors it.
2. **Classification is content-based and happens server-side in `_ingest_one`**, which
   already has the bytes. GAEB suffix -> `LV_DOCUMENT`; PDF with an XFA packet, or an
   AcroForm with `>= FORM_MIN_FIELDS` (3) non-pushbutton fields -> `FORM_DOCUMENT`;
   everything else -> `PROSE_DOCUMENT`. The client-side `classifyDocumentType` mirror in
   `ui/src/lib/documentType.ts` is deleted; the UI reads `document_type` from the server.
3. **Role is a property of the Formblatt, keyed by `(family, number)`, looked up from the
   filename.** Order: filename token -> role table; else Bieter title keyword -> `BIETER`;
   else `UNBEKANNT`. The same number means different things in different families
   (HVA B-StB 103 = Nachunternehmerleistungen, Bieter; NLStBV 103 = Vorzulegende
   Unterlagen, Vergabestelle), so there is one table per family, never one flat table.
4. **Only `BIETER` is skipped.** `VERGABESTELLE` and `UNBEKANNT` are extracted. A wrong
   table row that hides a document is the failure mode to avoid; an unknown form that gets
   indexed is cheap. `UNBEKANNT` is shown as such in the UI so the table can be extended.
5. **Skipped is an ingest job status, not "no job row".** `IngestStatus.SKIPPED` is set at
   enqueue time. The console keeps one row per document, `claim_next` never claims it
   (it only claims `queued` or expired `running`), and the Projektinfo claim rule ("no
   queued or running ingest jobs") is unaffected. "Trotzdem indexieren" is the existing
   requeue endpoint: it resets the job to `queued` and the worker ingests the form like
   any other, **because the worker dispatches on `document_type`, never on role**. Role
   only gates the automatic enqueue.
6. **The form extractor produces two things from one pass**: `source_lines` (full reading
   order text, so thumbnails, the source-line table, chunking and the chunk viewer keep
   working unchanged) and `form_fields` (structured rows for the UI key/value tab and for a
   later deterministic Projektinfo read). No new chunk model: `ChunkDraft` with
   `source_doc_type=FORM`.
7. **XFA is extracted from the embedded XML, never from the rendered page.** The
   `template` packet is walked in document order: `<draw>` text becomes a line (this is
   where the BVB prose of FB 352-B lives), `<field>` becomes `caption: value` with the
   value looked up in the `datasets` packet by the same subform path. Scripts are not
   evaluated; fields hidden only by script are emitted anyway.
8. **AcroForm forms keep `pdftotext` for the page text** (static text + rendered text-field
   appearances, with geometry) and add what it cannot see: one `label: ja` / `label: nein`
   line per checkbox or radio field that has a `/TU` label, appended after that page's
   lines. The `form_fields` rows come from `get_fields()` with the page taken from the
   widget annotation.
9. **Chunking is per section, not per 1000 characters.** The extractor emits a heading
   line (`FORM_SECTION_PREFIX = "## "`) at each section start: a named subform directly
   under the page subform for XFA (`Kopf`, `Anlagen`, ...), `Seite n` for AcroForm.
   `chunk_form` starts a new chunk at every heading, never splits a line, caps a chunk at
   `CHUNK_SIZE` and repeats the heading on a continuation chunk.
10. **Thumbnails are still generated.** For XFA they show the placeholder page; the detail
    dialog opens on the Felder tab for forms so that is not the first thing seen. No
    attempt to render XFA.
11. **Retrieval scope includes `FORM` wherever it includes `DOCUMENT`**: the SIMPLE filter
    and `plus_filter` in `client.py`, and the citation branch at
    `retrieval/service.py:310` (a FORM chunk carries pages like a DOCUMENT chunk). No
    boosting of forms in this task.
12. **The old upload flow goes through the same `_ingest_one`**, so forms uploaded one by
    one are handled identically to ZIP contents.

## Current state (read before changing)

- `server/shared/services/project_service.py:343` `_classify_document_type(file_name)`:
  suffix only. Called from `_ingest_one` (`:321`), which creates the Document, puts the
  raw bytes in storage and enqueues an `IngestJob`. `INGESTIBLE_SUFFIXES` (`:70`) filters
  the ZIP; `_count_pdf_pages` (`:482`) already opens every PDF with pdfplumber.
- `server/shared/services/ingestion/ingestion_service.py:100` `ingest_document`: branches
  on `is_gaeb_lv_file(document.file_name)`; the PDF path is thumbnails -> LangChain ->
  `extract_source_lines` -> `chunk_document` -> `_embed_and_index(..., SourceDocType.DOCUMENT)`.
- `server/shared/services/ingestion/extraction.py` `extract_source_lines` /
  `parse_bbox_layout`: poppler `pdftotext -bbox-layout`, one `NewSourceLine` per `<line>`
  (`document_uuid, line_id, page, bbox, line_text`).
- `server/shared/services/ingestion/chunking.py` `chunk_document` + `ChunkDraft`;
  `SOURCE_DOC_FIELD_DOCUMENT = "sourcelines.line_text"`, `CHUNK_SIZE = 1000`.
- `server/shared/models/enums.py`: `DocumentType {LV_DOCUMENT, PROSE_DOCUMENT}`,
  `SourceDocType {LV_ITEM, LV_TEXT, DOCUMENT}`, `IngestStatus {queued, running, done,
  failed}`. `documents` and `ingest_jobs` tables build their CHECK constraints from these
  enums; the SQL migrations must mirror the new members.
- `server/shared/services/ingestion/status_stream.py:_event_for_row` maps job status to
  the SSE event the project page renders (`IngestStatusCell.tsx` switches on it).
- `server/shared/clients/search/client.py:~140` (SIMPLE filter: `DOCUMENT` only) and
  `plus_filter` (`:146`). ES mapping is strict; `source_doc_type` is a `keyword`, so a new
  value needs no mapping change.
- `server/shared/services/retrieval/service.py:310`: `chunk.source_doc_type is not
  SourceDocType.DOCUMENT` picks the LV citation shape.
- `server/shared/models/document_schema.py`: `DocumentRead`, `DocumentDetailRead`
  (chunk counts per source, cost).
- UI: `ui/src/lib/documentType.ts` (constants + the filename mirror),
  `ui/src/views/main/ProjectDetails.tsx:279-345` (type badge, `IngestStatusCell`, the
  NLP-Analyse button gated on `PROSE_DOCUMENT` + done, `IngestButton`),
  `ui/src/views/main/UploadDocumentDialog.tsx:74-90` (predicted badge per picked file),
  `ui/src/views/main/DocumentDetailDialog.tsx` (tabs Thumbnails / Chunks / Ingestion Log,
  header `Meta` grid), `ui/src/views/main/IngestConsoleView.tsx:45` (status filter
  options), `ui/src/api/ingest.ts` (`DocIngestStatus`, `toStatus`).
- `pypdf==6.12.2` is already a dependency (LangChain's `PyPDFLoader` uses it).

## Role table (code, not a database table)

The table is a module-level literal in `forms/role.py`: one frozen tuple of
`FormblattSpec(family, number, title, role)` rows, from which the per-family lookup dicts
are derived at import time. It is not a Postgres table and not an enum: it changes a few
rows a year when the Bund revises the VHB/HVA, which is the cadence of a code change;
classification runs inside `_ingest_one` before anything is written and must not need a
connection; and the whole table is asserted row by row in `test_role.py`. If roles ever
need editing from the UI, `classify_form_role` keeps its signature and the tuple becomes
a repository read. The rows below **are** that literal; they were taken from the
filenames in the training corpus (every row is observed), not from memory. Arthur reviews
them before merge.

Token shapes on the basename, case-insensitive, matched in this order; first match wins.
`V` = Vergabestelle, `B` = Bieter.

**WSV** (`FB[ _-]?(\d{3}[a-z]?)-B`), `form_id` rendered `FB 312-B`:

| number | title | role |
|---|---|---|
| 312-B | Aufforderung zur Abgabe eines Angebots | V |
| 313-B | Gewichtung der Zuschlagskriterien | V |
| 317-B | Verzeichnis der vorzulegenden Unterlagen | V |
| 322-B | Teilnahmebedingungen | V |
| 331-B | Angebotsschreiben | B |
| 333a-B | Eigenerklärung zur Eignung | B |
| 341-B | Leistungsbeschreibung Titelblatt | V |
| 351-B | Zusätzliche Vertragsbedingungen | V |
| 352-B | Besondere Vertragsbedingungen | V |
| 392-B | Verzeichnis der Leistungen anderer Unternehmer | B |
| 393-B | Verpflichtungserklärung anderer Unternehmer | B |

**HVA B-StB** (`HVA[ _-]?B[ _-]?StB[ _-]?(\d{3})`), `form_id` rendered `HVA B-StB 121`. A
variant suffix (`104_2`, `121_EV`) is part of the same number:

| number | title | role |
|---|---|---|
| 101 | Teilnahmebedingungen National | V |
| 102 | Teilnahmebedingungen EU | V |
| 103 | Unterauftragnehmer-/Nachunternehmerleistungen | B |
| 104 | Eignungsleihe wirtschaftliche und finanzielle Leistungsfähigkeit | B |
| 105 | Verpflichtungserklärung | B |
| 106 | Erklärung Bietergemeinschaft | B |
| 107 | Eigenerklärung Eignung | B |
| 108 | Information Datenschutz | V |
| 109 | Vorzulegende Unterlagen | V |
| 111 | Aufforderung zur Angebotsabgabe | V |
| 112 | EU Aufforderung zur Angebotsabgabe | V |
| 121 | Angebotsschreiben (also `_EV`) | B |
| 131 | Besondere Vertragsbedingungen | V |
| 132 | Weitere Besondere Vertragsbedingungen | V |
| 144 | Titelblatt Leistungsbeschreibung | V |
| 152 | Bewerbungsbedingungen Teilnahmewettbewerb EU | V |
| 153 | Erklärung Bewerbergemeinschaft | B |
| 155 | Aufforderung Teilnahmewettbewerb EU | V |
| 157 | Teilnahmeantrag | B |
| 158 | Vorzulegende Unterlagen Teilnahmewettbewerb | V |

`HVA_B_StB_Eignungsleihe_technische_und_berufliche_Leistungsfaehigkeit.pdf` has no number
and resolves through the `eignungsleihe` keyword.

**VHB / FB without `-B`** (`(?:VHB|FB|Formblatt)[ _-]?(\d{3})(?![a-z]?-B)`), `form_id`
rendered `VHB 221`. WSV 4xx without `-B` share this shape and do not collide with VHB
numbers:

| number | title | role |
|---|---|---|
| 124 | Eigenerklärung | B |
| 211 | Aufforderung zur Abgabe eines Angebots | V |
| 212 | Teilnahmebedingungen | V |
| 213 | Angebotsschreiben | B |
| 214 | Besondere Vertragsbedingungen | V |
| 216 | Verzeichnis der vorzulegenden Unterlagen | V |
| 221 | Zuschlagskalkulation | B |
| 222 | Kalkulation über die Endsumme | B |
| 233 | Verzeichnis der Nachunternehmerleistungen | B |
| 234 | Erklärung Bieter-/Arbeitsgemeinschaft | B |
| 235 | Verzeichnis der Leistungen und Kapazitäten anderer Unternehmen | B |
| 236 | Verpflichtungserklärung anderer Unternehmen | B |
| 241 | Abfall | B |
| 244 | Datenverarbeitung | B |
| 401 | Erklärung Bieter-/Arbeitsgemeinschaft (WSV numbering) | B |
| 421 | Erklärung Holzprodukte (WSV numbering) | B |

**EFB-Preis** (`EFB[ _-]*Preis`): `B`, `form_id` `EFB-Preis`.

**Not a token: a bare numeric prefix** (`101-Aufforderung ...`, `211-Aufforderung_Sermer
Straße`, `501-K6-Bodengutachten`). That is the tender's own ordering of its documents, not
a Formblatt number: NLStBV `401-` is BVB (V) while WSV `FB 401` is Bietergemeinschaft (B).
Files with only such a prefix fall through to the keyword rule or `UNBEKANNT`. In the
corpus all of them are flattened PDFs anyway and stay prose.

**Bundles.** `FB 211, 212, 214, 213, 233.pdf` is several Formblätter in one PDF, mixing V
and B. First token wins (211 -> V), so it is ingested, which is the safe direction. Not
split in this task.

**Bieter title keywords** (substring, case-insensitive, umlauts and `ae/oe/ue` spellings):
`angebotsschreiben`, `eigenerklärung`, `efb`, `eignungsleihe`, `verpflichtungserklärung`,
`bietergemeinschaft`, `bewerbergemeinschaft`, `arbeitsgemeinschaft`, `nachunternehmer`,
`unterauftragnehmer`, `teilnahmeantrag`, `nachweis`. Not `verzeichnis` (ambiguous:
FB 216/317-B are Vergabestelle, FB 235/392-B are Bieter; the table decides those).

Expected on the corpus: 3 forms end up `UNBEKANNT` (Baustelleninformationsschild,
Informationspflicht ThürVgG, TTSiB Projektdatenblatt), all Vergabestelle-side, all ingested.

## Changes

### 1. Enums, model, table, migration (backend)

- `DocumentType.FORM_DOCUMENT = "FORM_DOCUMENT"`; `SourceDocType.FORM = "FORM"`;
  `IngestStatus.SKIPPED = "skipped"`.
- `FormRole(StrEnum)` in `enums.py`: `VERGABESTELLE = "vergabestelle"`, `BIETER =
  "bieter"`, `UNBEKANNT = "unbekannt"`.
- `documents` gains `form_role` (text, nullable, CHECK in `FormRole`) and `form_id` (text,
  nullable; e.g. `FB 312-B`, `HVA B-StB 121`, `VHB 221`, `EFB-Preis`). CHECK
  `document_type_form_role`: `(document_type = 'FORM_DOCUMENT') = (form_role IS NOT
  NULL)`. `form_id` may be null on a form (`UNBEKANNT` by keyword or nothing).
- `Document` / `NewDocument` / `DocumentRead` / `DocumentDetailRead`: `form_role: FormRole
  | None = None`, `form_id: str | None = None`.
- New table `form_fields` (`server/shared/db/tables/form_fields.py`, register in
  `tables/__init__.py`):

  | column | type | notes |
  |---|---|---|
  | `document_uuid` | uuid FK documents ON DELETE CASCADE | |
  | `field_order` | integer NOT NULL | reading order within the document |
  | `section` | text NOT NULL | subform name (XFA) or `Seite n` (AcroForm) |
  | `name` | text NOT NULL | field name (`VE_EINREICH_DAT_L__SB_`, `/T`) |
  | `label` | text | caption / `/TU`; null when the form has none |
  | `value` | text NOT NULL | checkbox as `ja` / `nein`, radio as selected caption or export value |
  | `page` | integer NOT NULL | 1 for XFA |

  PK `(document_uuid, field_order)`. Models `NewFormField` / `FormField`, repository
  `server/shared/repositories/form_fields.py` with `add_many`, `list_for_document`,
  `delete_for_document`; UoW attribute `form_fields`. Re-ingest deletes then re-adds.
- Migration `sql/24_form_documents.sql` in the header style of `sql/23`: add the two
  columns, drop and re-create `document_type_valid` with the third value, add the role
  CHECK, re-create `status_valid` on `ingest_jobs` **and** on `project_info_jobs` (both
  are built from `IngestStatus`) with `skipped`, create `form_fields`. Idempotent.
- `ingestion_cost` / `IngestionResult`: add `form_fields: int`.

### 2. Detection and role (`server/shared/services/ingestion/forms/`)

New sub-package; the ingestion module already has >10 files, this is its own grouping.

- `detect.py`: `FormKind(StrEnum) {XFA, ACROFORM}`; `FORM_MIN_FIELDS = 3`;
  `detect_form_kind(pdf_bytes) -> FormKind | None`. pypdf: `/XFA` under `/AcroForm` ->
  `XFA`; else count `get_fields()` entries whose `/FT` is not a pushbutton (`/Btn` with
  flag bit 17) and return `ACROFORM` when `>= FORM_MIN_FIELDS`. Any pypdf exception ->
  `None` with one warning log (the PDF then goes down the prose path, which is what
  happens today). Called once per PDF in `_ingest_one`; it runs in milliseconds.
- `role.py`: `FormFamily(StrEnum) {WSV, HVA_B_STB, VHB, EFB}`; `FormblattSpec`
  (frozen Pydantic model or `NamedTuple`: `family, number, title, role`);
  `FORMBLAETTER: tuple[FormblattSpec, ...]` holding the rows of the role table above, one
  line each; the per-family token regexes; `_ROLE_BY_FAMILY: dict[FormFamily, dict[str,
  FormblattSpec]]` derived from the tuple at import time (duplicate `(family, number)`
  raises at import); `BIETER_KEYWORDS`; `format_form_id(family, number)` (`FB 312-B`,
  `HVA B-StB 121`, `VHB 221`, `EFB-Preis`); and `classify_form_role(file_name) ->
  tuple[FormRole, str | None]` returning `(role, form_id)`. Pure function, no I/O.
- `project_service.py`: replace `_classify_document_type(file_name)` with
  `classify_document(file_name, data) -> tuple[DocumentType, FormRole | None, str |
  None]`; `_ingest_one` writes the three values into `NewDocument` and, when role is
  `BIETER`, adds the job with `status=IngestStatus.SKIPPED` (`NewIngestJob` gains an
  optional `status`, default `queued`; `IngestJobRepository.add` honours it). Update the
  docstring that mentions the UI mirror.

### 3. Form extraction (`forms/extraction.py`, `forms/xfa.py`, `forms/acroform.py`)

- `FormExtraction(BaseModel)`: `lines: list[NewSourceLine]`, `fields: list[NewFormField]`.
- `extract_form(pdf_bytes, document_uuid, kind) -> FormExtraction`.
- `FORM_SECTION_PREFIX = "## "`, `CHECKED = "ja"`, `UNCHECKED = "nein"`, label/value
  separator `": "`. These are contract literals shared with `chunk_form` and the UI tab;
  module constants, referenced on both sides.
- **XFA** (`xfa.py`): read the `/XFA` array into `{packet_name: bytes}`; parse `template`
  and `datasets` with `xml.etree`. Walk the template in document order from the page
  subform (`Page1`) down, carrying the subform-name path. Named subforms directly under the
  page open a section (heading line). `<draw>` with `<value><text>` or
  `<value><exData>` (XHTML, take `itertext()`) -> one line. `<field>`: caption from
  `<caption><value><text>`, value from the datasets leaf at the same path (`_L__SB_`
  suffix names match 1:1); `<ui><checkButton>` -> `ja` if the value equals the first
  `<items><text>` on-value, else `nein`; `<exclGroup>` (radio, `Optionsfeldliste`) -> the
  caption of the child field whose on-value equals the group value; `<ui><imageEdit>`,
  `<ui><button>`, `presence="hidden"` and names matching `ID_|validate|Formularbutton` are
  skipped. A text field without a value is skipped. Lines are `NewSourceLine(page=1,
  bbox=(0, 0, 0, 0))`, `line_id` sequential. `fields` rows for every emitted field.
- **AcroForm** (`acroform.py`): `lines` = `extract_source_lines(pdf_bytes, document_uuid)`
  from the existing module, grouped by page with a `## Seite n` heading inserted before
  each page's first line, then for each page the checkbox/radio lines for fields that
  have a `/TU`; `line_id` re-numbered after insertion. `fields` = all non-pushbutton
  fields from `get_fields()` in widget reading order (page, top-to-bottom, left-to-right
  from `/Rect`, converted to top-origin like `parse_bbox_layout`), value `/V` for text
  fields, `ja`/`nein` for checkboxes, the export value for radios, empty text fields
  omitted. `label` = `/TU` or null, `section` = `Seite n`.
- Both paths never emit the pdftotext placeholder page (XFA does not call pdftotext).

### 4. Form chunking (`chunking.py`)

- `chunk_form(source_lines, *, project_uuid, document_uuid) -> list[ChunkDraft]`: walk
  the ordered lines; a line starting with `FORM_SECTION_PREFIX` closes the current chunk
  and opens a new one with that heading; otherwise append the line unless the chunk
  would exceed `CHUNK_SIZE` characters, in which case close it and open a continuation
  chunk starting with the same heading. `source_doc_type=SourceDocType.FORM`,
  `source_doc_field=SOURCE_DOC_FIELD_DOCUMENT`, `source_doc_pages` = the distinct pages of
  the chunk's lines, `chunk_index` sequential. No overlap.

### 5. Worker path (`ingestion_service.py`)

- `ingest_document` dispatches on `document.document_type`: `LV_DOCUMENT` ->
  `_ingest_gaeb_document` (unchanged), `FORM_DOCUMENT` -> new `_ingest_form_document`,
  `PROSE_DOCUMENT` -> the existing PDF path. The `is_gaeb_lv_file` call there goes
  (classification happened at enqueue; the type is the discriminator now).
- `_ingest_form_document`: download -> thumbnails (as today) -> `IngestPhase.EXTRACT`:
  `detect_form_kind` again on the bytes (the kind is not stored), `extract_form`, in one
  UoW `source_lines.add_many(lines)` and `form_fields.delete_for_document` +
  `add_many(fields)`, emit `SOURCE_LINES_PERSISTED` -> `IngestPhase.CHUNK`: `chunk_form`,
  `_embed_and_index(..., SourceDocType.FORM, ...)`, emit `DOCUMENT_CHUNKS_INDEXED`. No
  `LANGCHAIN` phase, `langchain_chunks=0`. Activity lines: "form (xfa|acroform): n fields,
  m sections", "extracted n source lines", counts and durations as the prose path does.
- Re-ingest of a form must also archive its previous `FORM` chunks: `archive_source` is
  called per `(source_doc_uuid, type)` and already takes the type, so pass `FORM`.
- `status_stream.py:_event_for_row`: `IngestStatus.SKIPPED` -> new `IngestSkipped(event=
  "ingest_skipped")` SSE model in `ingest_schema.py` (add to `BODY_MODELS`). The project
  status `counts` include `skipped`.

### 6. Search and retrieval

- `client.py`: the SIMPLE filter and `plus_filter` take `[DOCUMENT, FORM]` where they
  took `DOCUMENT`; update the `plus_filter` docstring.
- `retrieval/service.py:310`: treat `FORM` like `DOCUMENT` (page citation), so the
  condition becomes membership in `{LV_ITEM, LV_TEXT}` rather than `is not DOCUMENT`.
- grep `SourceDocType.DOCUMENT` once more across `server/` after the change; every
  remaining site is either the ingest path (correct) or needs `FORM` too.

### 7. API

- `GET /projects/{project_uuid}/documents/{document_uuid}/form-fields` ->
  `list[FormFieldRead]` (`field_order, section, name, label, value, page`), service method
  on `DocumentDetailService` (thin route, logic in the service). 404 for a non-form.
- `DocumentRead` / `DocumentDetailRead` carry `form_role`, `form_id` (section 1).
- `POST /ingest-jobs/{job_uuid}/requeue` already resets to `queued`; it now also accepts a
  `skipped` job (check `IngestJobRepository.requeue` has no status guard that excludes
  it). This is "Trotzdem indexieren".
- `npm run gen:types` after the backend compiles.

### 8. UI

- `ui/src/lib/documentType.ts`: keep `DOCUMENT_TYPE_LV`, `DOCUMENT_TYPE_PROSE`, add
  `DOCUMENT_TYPE_FORM`; delete `classifyDocumentType` and the mirror comment; keep
  `GAEB_LV_PATTERN` only if `UploadDocumentDialog` still needs it (see next item). Add
  `formRoleLabel(role)`: `vergabestelle` -> "Vergabestelle", `bieter` -> "Bieter",
  `unbekannt` -> "Rolle unbekannt".
- `UploadDocumentDialog.tsx`: the per-file badge can no longer predict the type from the
  name. Show "GAEB" for `.d83/.x83` and "PDF" otherwise; the real type appears in the
  document table after upload. Keep the LV hint block gated on the GAEB pattern.
- `ProjectDetails.tsx` documents table: badge colour per type (`LV` amber as today,
  `FORM` indigo, `PROSE` zinc), badge text the type without `_DOCUMENT`; for a form a
  second line under the file name: `form_id ?? 'Formblatt'` + ` · ` + `formRoleLabel`.
  The NLP-Analyse button stays gated on `PROSE_DOCUMENT` (it reflows prose). `IngestButton`
  is also shown active-able for `skipped` (it requeues).
- `IngestStatusCell.tsx`: `case 'skipped'`: `Badge color="amber"` "Skipped", `title`
  "Bieterformular, nicht indexiert". `ui/src/api/ingest.ts`: `toStatus` maps
  `ingest_skipped` -> `{status: 'skipped'}`; `IngestStatusValue` gains it (generated).
- `IngestConsoleView.tsx`: add `skipped` to the status filter options; "Active" (decision 4
  of task 06) does **not** include skipped.
- `DocumentDetailDialog.tsx`: for `FORM_DOCUMENT` add a first tab `Felder (n)` rendering
  the form-fields endpoint as a table grouped by `section` (section heading row, then
  `label ?? name` | `value` | page), opened by default for forms; the header `Meta` grid
  shows `Formblatt` (form_id) and `Rolle` instead of the LangChain chunk count, and the
  Chunks tab hides the `simple / langchain` toggle for forms (there are none). New hook
  `useDocumentFormFields(projectUuid, documentUuid)` in `ui/src/api/documents.ts` with a
  key in the existing factory.

### 9. Documentation

- `APPLICATION_ARCHITECTURE.md`: `documents.form_role/form_id`, the `form_fields` table in
  the ERD, the third `DocumentType`, `IngestStatus.skipped`.
- `AI_ARCHITECTURE.md`: the ingestion branch (LV / FORM / PROSE), what the form extractor
  reads, that forms skip the LangChain pass, `SourceDocType.FORM` in both retrieval scopes.
  Fix the stale "AcroForm-capable" sentence to say what poppler does and does not see.
- `GLOSSARY.md`: Formblatt, Vergabestelle, Bieter (as roles of a form), XFA, AcroForm.
- `extraction.py` module docstring: narrow its AcroForm claim to text-field appearances.

### 10. Tests

Unit (`tests/unit/services/ingestion/forms/`):
- `test_role.py`: every row of the tables resolves; family collision (`HVA_B_StB_103` ->
  Bieter vs a hypothetical `103-...` NLStBV name -> `UNBEKANNT`); keyword fallback with
  `ae`/`ä` spellings; the three expected `UNBEKANNT` names; `form_id` rendering.
- `test_xfa.py`: inline `template` + `datasets` XML (trimmed from FB 312-B: a text field,
  a checkbox on/off, an `exclGroup`, a `<draw>` paragraph, a hidden field, the image and
  button fields) -> expected lines with headings and expected `form_fields`.
- `test_acroform.py`: a pypdf-built single-page PDF with two text fields, a checked and an
  unchecked checkbox with `/TU`, a pushbutton; assert the pushbutton is excluded, the
  page heading, the `ja`/`nein` lines and the field order.
- `test_detect.py`: zero-field `/AcroForm` dict -> `None`; two fields -> `None`; three
  -> `ACROFORM`; an `/XFA` entry -> `XFA`; garbage bytes -> `None`.
- `test_chunking.py` (extend): `chunk_form` splits on headings, never mid-line, repeats
  the heading on continuation, sets `FORM` and pages.
- `test_project_service.py` (extend): `classify_document` on a GAEB name, a 0-field PDF,
  a 3-field PDF; `_ingest_one` enqueues `skipped` for a Bieter form and `queued`
  otherwise.
- `test_status_stream.py` (extend): `skipped` -> `ingest_skipped`.

Integration (`tests/integration/`):
- `form_fields` repository round trip; the form-fields route; an end-to-end
  `ingest_document` on a `FORM_DOCUMENT` with a mocked embeddings client, asserting
  `FORM` chunks and no LangChain call.
- Corpus check, skipped when `server/training` is absent: run `detect_form_kind` +
  `classify_form_role` over every PDF there and assert the counts above (92 forms, 12
  XFA, 3 `UNBEKANNT`, no `LV Los*.pdf` detected as a form). This is the regression test
  for the "AcroForm dict with zero fields" trap.

Fixtures: build the AcroForm fixture in the test with pypdf; keep the XFA test on inline
XML. Do not copy training PDFs into the repo.

## Known limitations (state them in the docs, do not fix here)

- XFA thumbnails show Adobe's placeholder page.
- XFA lines have no geometry (`bbox` all zero); anything that highlights source lines on a
  thumbnail gets nothing for XFA.
- Script-driven visibility in XFA is not evaluated; a few lines of conditional boilerplate
  may be emitted that the rendered form would hide.
- `UNBEKANNT` forms are indexed with no role filter; Projektinfo retrieval may pick a
  pre-filled Kopf from one of them, which is the same information as the Aufforderung
  carries, so it is harmless.
- ~~Flattened Formblätter (zero fields) remain `PROSE_DOCUMENT`, which is correct for
  extraction, but they get no `form_id` and no role badge.~~ (task 08)

## Done means

- `uv run pytest` green; `uvx ruff check` / `format` clean on touched files only.
- `npm run gen:types`, `npm run build` green.
- On a scratch DB: `sql/24` applied twice without error.
- Manual: create a project from the WNA Berlin ZIP. Expect 12 `FORM_DOCUMENT`s, of which
  FB 331-B, 333a-B, 392-B, 393-B, 401, 421 are `skipped` with role Bieter; FB 312-B,
  313-B, 317-B (both copies), 341-B, 352-B are `done` with role Vergabestelle, and the
  Felder tab of FB 312-B shows Vergabestelle, Vergabenummer `26/001`, Einreichungsdatum
  `2026-10-15`, Zuschlagsfrist `14.12.2026`. The Projektinfo job then fills
  `vergabenummer` and `vergabestelle` from them. Requeue one skipped form and confirm it
  ingests as a form. Upload one 0-field "AcroForm" PDF (any plan from the corpus) through
  the old dialog and confirm it stays `PROSE_DOCUMENT`.
