# Tasks: NLP Analysis Modal

## 1. Foundation

- [x] 1.1 Add `spacy` and `docling` to `pyproject.toml`; `uv sync`; download `de_core_news_lg` in the Docker build and document local `python -m spacy download de_core_news_lg`
- [x] 1.2 Add `BlockType` StrEnum (PROSE, HEADING, LIST_ITEM, TABLE, CAPTION, FOOTNOTE, FURNITURE) and Pydantic models (`ReflowedBlock`, `SentenceInfo`, `PosStats`, request/response schemas) in `server/shared/models/`
- [x] 1.3 New tables `document_layout_regions` and `nlp_render_cache` in `server/shared/db/tables/`, wired into shared MetaData; repositories taking `AsyncConnection`

## 2. Layout inference

- [x] 2.1 `server/shared/services/nlp/layout.py`: render pages via `pdftoppm` from the MinIO raw PDF, run Docling layout model (lazy singleton), map regions to `(label, page, bbox)` in PDF-point coordinates
- [x] 2.2 Persist/lookup regions in `document_layout_regions` keyed by document uuid + model version
- [x] 2.3 Unit tests with recorded Docling output (no model in CI): region mapping, coordinate scaling, cache hit/miss

## 3. Reflow service

- [x] 3.1 `server/shared/services/nlp/reflow.py`: repetition heuristic (digit-run normalization + y-bucket, ≥50% of pages, min 3)
- [x] 3.2 Furniture union + line→region assignment by bbox center; block building in reading order with PROSE fallback for uncovered lines
- [x] 3.3 In-block reflow: dehyphenation (lowercase→drop, uppercase→keep), space join, adaptive paragraph breaks, cross-page merge; provenance as ordered `line_id` lists
- [x] 3.4 Golden tests from the spike corpus: L 40 (clean), B 246a (letterhead), Brücke Nr. 6 (roman numerals), incl. `gekommenen`/`SRT-Pendel` dehyphenation and page 8→9 sentence merge

## 4. Analysis + renders

- [x] 4.1 `server/shared/services/nlp/analysis.py`: lazy spaCy singleton, `nlp.pipe` over included blocks, sentence list + UD/STTS counts + per-tag token index
- [x] 4.2 `server/shared/services/nlp/render.py`: dep SVG with `nlp_render_cache` (sha256 of model+version+style+text), ent HTML via displacy `manual=True`
- [x] 4.3 Unit tests: include-list filtering, POS aggregation, cache keying incl. model-version invalidation

## 5. API

- [x] 5.1 `server/api/routes/nlp.py`: `GET /nlp/documents`, `GET /nlp/documents/{uuid}/text`, `POST /nlp/analyze`, `POST /nlp/render` (style + text body; hashes are not reversible) — thin wrappers over the services
- [x] 5.2 Integration tests against the seeded corpus
- [x] 5.3 Regenerate `ui/src/types/generated.ts` (`npm run gen:types`)

## 6. UI modal

- [x] 6.1 `ui/src/api/nlp.ts`: query-key factory + hooks (documents, text, analyze with include_blocks, render)
- [x] 6.2 Modal shell + document picker grouped by project; block-type toggles
- [x] 6.3 Text tab: reflowed blocks + original-lines toggle with dimmed furniture/excluded blocks
- [x] 6.4 Sentences tab: block-grouped sentence list, dep/ent buttons, on-click render injection in scoped scrollable containers
- [x] 6.5 POS tab: normalized horizontal bar chart, UD/STTS toggle, click-through token list
- [x] 6.6 Entry point in the app (where the modal opens from)

## 7. Verification & docs

- [x] 7.1 End-to-end pass over all 10 Baubeschreibungen in the modal; eyeball reflow quality via the original-lines toggle
- [x] 7.2 Update `APPLICATION_ARCHITECTURE.md` (new tables/endpoints) and `AI_ARCHITECTURE.md` (reflow pipeline + flowchart)
