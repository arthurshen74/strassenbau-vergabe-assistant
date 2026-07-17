# NLP Analysis Modal

## Why

Arthur's NLP course graded project (requirement 1: text pre-processing — segmentation and POS tagging) is being built into strassenbau as a learning tool, because the app already holds the corpus (Baubeschreibungen) and the Katalog store that later NER work (EntityRuler) will draw on. The existing `source_lines` are raw layout lines — hyphen-broken, footer-polluted, table-fragmented — and unusable for NLP without a reflow step. A layout-analysis spike (`nlp-playground/layout-spike/`, 4 Baubeschreibungen, 3 template families) settled the approach: a hybrid of the existing `pdftotext` extraction and Docling layout regions.

## What Changes

- New **document reflow service**: turns a document's `source_lines` into typed, ordered content blocks (prose/heading/list/table/furniture) using Docling layout regions joined by bbox, a repetition heuristic for furniture (union of both), German dehyphenation, and paragraph merging — with provenance from every block back to `line_id` ranges (page + bbox).
- New **NLP analysis API** (`/nlp/*`): list analyzable documents, return reflowed text, return sentence segmentation + POS statistics (spaCy `de_core_news_lg`), and serve per-sentence displacy renders (`dep` as cached SVG, `ent` as uncached HTML).
- New **NLP analysis modal** in the UI: three tabs — raw/reflowed text (with original-lines toggle), sentence list with per-sentence dep/ent render buttons, POS histogram (normalized coarse UD tags, toggle to fine STTS, click-through to tokens).
- Block-type **inclusion config**: which block types feed sentence analysis (default: prose, heading, list item); adjustable per request and surfaced as toggles in the modal.
- New backend dependencies: `spacy` (+ `de_core_news_lg` model), `docling`.

Out of scope: NER/EntityRuler (later phase), table-heavy appendix documents (Baustoffverzeichnis — different document class), summarization/similarity (later course requirements).

## Capabilities

### New Capabilities

- `document-reflow`: converting a document's stored `source_lines` into classified, ordered, dehyphenated content blocks with line-level provenance; layout-model region detection, furniture removal, block typing, reflow rules.
- `nlp-analysis-api`: HTTP surface for the NLP feature — document listing, reflowed text, sentence/POS analysis with block-type inclusion parameters, displacy render generation and caching.
- `nlp-analysis-modal`: the three-tab UI modal — text view, sentence view with renders, POS histogram — including the block-type inclusion toggles.

### Modified Capabilities

_None (first change in this OpenSpec store; no existing specs)._

## Impact

- `server/shared/services/`: new `nlp/` service package (reflow, analysis, render cache). Layout inference and spaCy models lazy-load on first use — API boot must not eat their memory.
- `server/api/routes/`: new thin `nlp.py` route file.
- `server/shared/db/tables/`: new `nlp_render_cache` table (keyed by content hash) and a `document_layout_regions` cache table (Docling output per document; PDFs are immutable).
- `ui/src/api/`: new `nlp.ts` resource file (React Query hooks + query keys). `ui/src/types/generated.ts` regenerated.
- `ui/src/components/` or `ui/src/views/`: new modal component group.
- `pyproject.toml`: `spacy`, `docling` added; Docker worker/api images grow by the model weights (~1 GB); first-run model download needs network.
- MinIO: raw PDFs read once per document for page rendering during layout inference.
