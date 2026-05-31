# LV Parse

The detail behind the LV branch in [INGESTION](./INGESTION.md): how the `SourceLine` rows for an LV document become `LVItem` records (and, downstream, `SimpleChunk`s). The PDF→`SourceLine` extraction is no longer described here — it's the common ingestion stage that runs on every PDF; this document starts from the `SourceLine` rows it produces.

## Summary

Given the `SourceLine` rows for an LV document, this stage produces one `LVItem` per position (OZ). Its guiding principle is a strict division of labor: **deterministic code owns the binding text, the LLM owns only segmentation.** The LLM reads a line-numbered rendering of the `SourceLine` text and says which lines belong to which position and field — but it never reproduces the contractual `lang_text` and never emits coordinates. Code then slices the verbatim text out of `SourceLine` by line span, resolves "wie in voriger Position" back-references into `lang_text_resolved`, and attaches governing Hinweise.

```mermaid
flowchart TD
    SL[("SourceLine — Postgres<br/>(from the common ingestion stage)")]
    NUMDOC["render line-numbered text for the LLM<br/>line_id-prefixed; optional furniture strip"]
    SL --> NUMDOC

    NUMDOC --> LLM["LLM extraction (text input, no vision)<br/>each position: field -> line span OR parsed value"]
    LLM --> JSON["JSON per position<br/>values: oz, stl_nr, menge, einheit<br/>line spans: kurz_text, lang_text, hinweis<br/>+ linked_oz"]

    JSON --> POST["code post-processing"]
    SL --> POST
    POST --> V["validate: oz monotonic, spans in range,<br/>lang_text non-empty, menge numeric"]
    V --> SLICE["slice verbatim from SourceLine by span<br/>map span -> page(s)"]
    SLICE --> RESOLVE["resolve back-refs over ordered positions<br/>compose lang_text_resolved; attach Hinweise"]
    RESOLVE --> LVI[("LVItem — Postgres")]
    LVI --> CHUNK["chunk lang_text_resolved"]
    CHUNK --> SC[("SimpleChunk — Elasticsearch")]
```

## Steps

1. **SourceLine (input)** — produced by the common ingestion stage; one row per visual line with `line_id`, `page`, `bbox`, `line_text`. This is the verbatim source of truth the rest of the stage slices from.
2. **Render line-numbered text** — concatenate the document's `SourceLine` rows, each prefixed with its `line_id`, into the plain text the LLM will read. Strip repeating page furniture (headers/footers) from this rendering — `SourceLine` itself stays complete. This is the only thing the LLM sees.
3. **LLM extraction (text, no vision)** — the model returns each position with every field mapped to a line span (prose) or a parsed value (short header-line tokens). Segmentation only — no reproduced text, no coordinates.
4. **JSON per position** — _values_ for `oz`, `stl_nr`, `menge`, `einheit`; _line spans_ for `kurz_text`, `lang_text`, `hinweis`; plus `linked_oz` when the position reads "wie in voriger Position."
5. **Code post-processing** — consumes the JSON together with the `SourceLine` rows. Everything from here is deterministic.
6. **Validate** — OZ monotonic, line spans in range and non-overlapping, `lang_text` non-empty, `menge` numeric, `stl_nr` well-formed. Fail loudly or route low-confidence positions to review.
7. **Slice verbatim + map to pages** — cut the exact text out of `SourceLine` by line span, and resolve each span to its page(s).
8. **Resolve back-refs + attach Hinweise** — for "wie in voriger Position" items, compose `lang_text_resolved` (predecessor body + delta, recursively for chains) while keeping `lang_text` verbatim; attach each Hinweis to the OZ or Titel it names.
9. **LVItem (Postgres)** — emit one record per position: `oz`, `kurz_text`, `lang_text`, `lang_text_resolved`, `menge`, `einheit`, `positions_typ`, `level`, `stl_nr`, `hinweis`, and the `linked_oz` / `prev_oz` / `next_oz` / `parent_oz` links.
10. **Chunk → SimpleChunk (Elasticsearch)** — chunk `lang_text_resolved` (sub-splitting long positions) into `SimpleChunk`s with `source_doc_type = LV_ITEM`, carrying the denormalized `oz` and `stl_nr`.
