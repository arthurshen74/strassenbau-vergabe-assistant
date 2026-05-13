# Ingestion Plan - Schriftsatz: PDF Transcribe + Filter + Translate CLI

## Context

The German legal document `klageerwiderung.2026.04.09.pdf` (Klageerwiderung from opposing counsel) needs page-by-page OCR + English translation to support response drafting. The existing assets — `transcribe.md`, `translate.md`, `submitExtraction.json`, `submitTranslation.json`, `substantiveStartPhrases.txt`, `.env` with `ANTHROPIC_API_KEY` — define the prompts, tool schemas, and cue phrases. The CLI renders each page at 300 DPI, extracts paragraphs via Sonnet 4.6 vision, filters out repeating headers/footers and pre-substantive procedural content, translates each surviving paragraph through an Opus 4.7 → Opus 4.6 → Sonnet 4.6 fallback ladder, renumbers paragraphs per-page, and emits a flat JSON array of `{page, paragraph, text, translation}` records.

## Deliverables

1. **`transcribe_translate.py`** — single-file CLI at the working-dir root.
2. **`requirements.txt`** — `python-dotenv`, `anthropic`, `pdf2image`, `tqdm`, `Pillow`.
3. **`substantiveStartPhrases.txt`** — one regex per line; blank/`#` lines ignored.

## CLI

```
python transcribe_translate.py <pdf_path> <output_file_path>
```

- `pdf_path` — input PDF.
- `output_file_path` — output JSON file; parent created if missing; overwritten if it already exists.
- Caches in `./.cache/<pdf_stem>/`:
  - `page_<NNN>.png` — 300 DPI page renders.
  - `page_<NNN>.paragraphs.json` — per-page extraction results.
  - `translations/<hash16>.json` — per-paragraph translation cache, keyed on `sha256(text)[:16]`.
  - `filtered.json` — audit log of dropped paragraphs.
- Loads `.env` from CWD via `python-dotenv`.

## Pipeline

```
render → extract (cached) → migrate translation cache → filter header/footer
       → filter substantive-start → write filter audit → translate (hash-cached)
       → renumber → write output → report
```

### 1. Render pages — `pdf2image` + poppler

300 DPI PNGs to `<cache>/page_<NNN>.png`. Reused on re-runs.

### 2. Extract paragraphs — Sonnet 4.6 vision

One call per page (sequential), forced `submit_extraction` tool call. Outputs cached as `page_<NNN>.paragraphs.json`. Includes a state-machine repair for cases where Sonnet emits `paragraphs` as a stringified JSON array with unescaped `"` inside string values, plus a `temperature=0.5` retry if the first attempt is unrecoverable.

### 3. Cache migration

On startup, any `pNNN_paraNNN.json` files left in `<cache>/translations/` from the old positional cache scheme are converted to the new hash-keyed format (`<hash16>.json` with body `{hash, text, translation, model}`). Old files unlinked on success. Idempotent.

### 4. Header/footer filter

Normalize each candidate paragraph's text (trim, lowercase, collapse whitespace, mask digits with `_`). Inspect positions 1, 2, second-to-last, last of every page. Cluster by normalized text; any cluster whose size is in `{page_count, page_count - 1}` is a header/footer pattern. Every paragraph whose normalized text matches a pattern is dropped, even mid-page. The full frequency map is logged; a `WARN` is emitted whenever a dropped paragraph sits outside the inspected positions.

### 5. Substantive-start filter

- Fast path: load `substantiveStartPhrases.txt`, compile lines as `re.IGNORECASE` patterns, return the first paragraph whose `text` matches any pattern.
- Fallback (LLM): Sonnet 4.6, `temperature=0.0`, `max_tokens=64`, assistant-prefill JSON output (`{"page": ` + `stop_sequences=["}"]`), no tool use. Returns `{page, paragraph}`.
- Drop everything before `(start_page, start_paragraph)` in document order. If both regex and LLM return `None`, fail-open (keep everything).

### 6. Translate — Opus 4.7 → Opus 4.6 → Sonnet 4.6 ladder

Each paragraph is translated with a forced `submit_translation` tool call. Cache key is `sha256(text)[:16]`. Cache file body: `{hash, text, translation, model}`. On cache hit, the stored `text` is verified equal to the live text (collision insurance). The model fallback ladder runs per-paragraph: each model gets the full retry budget before falling back. Retries use exponential backoff with equal jitter, base 1s, capped at 120s, 8 attempts.

### 7. Renumber

Per-page in-place. Page numbers untouched; `paragraph` restarts at `1` within each page, preserving original within-page order.

### 8. Write output

Flat JSON array to `<output_file_path>`.

### 9. End-of-run report (stdout)

Pages processed; paragraphs extracted; paragraphs dropped (header/footer); paragraphs dropped (pre-substantive); substantive start matched by (regex/llm/none); paragraphs translated; total wall time; extract and translate latency stats.

## Error handling

- API calls: 8 attempts with exponential backoff + equal jitter (cap 120s). Covers overload (529) and rate-limit windows.
- Translation: per-paragraph cache + per-paragraph model ladder, so a transient outage on one model fails over to the next; reruns resume from the last successful paragraph.
- Extraction: per-page cache means re-runs skip completed pages; raw payloads on shape mismatch are dumped to `<cache>/page_NNN.error.json` for inspection.

## Verification

1. `brew list poppler >/dev/null || brew install poppler`
2. `pip install -r requirements.txt`
3. `python transcribe_translate.py klageerwiderung.2026.04.09.pdf out/klageerwiderung.2026.04.09.json`
4. Confirm:
   - Header/footer cluster table in stdout shows the recurring "Seite N von 18" pattern flagged.
   - Substantive start landed on the paragraph containing "Zur Begründung ist Folgendes auszuführen:" (`matched_by: regex`).
   - `.cache/<stem>/filtered.json` lists dropped paragraphs by category.
   - Output JSON: no header/footer paragraphs; page numbers verbatim; `paragraph` starts at 1 per page; every entry has a `translation`.
   - `.cache/<stem>/translations/` is populated with `<hash16>.json` files only (no `pNNN_paraNNN.json`).
