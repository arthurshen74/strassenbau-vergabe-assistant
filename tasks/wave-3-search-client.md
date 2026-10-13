# Wave 3 — Elasticsearch search client

Read `tasks/README.md` first. Independent of the Postgres waves; depends on `server/shared/config.py`
and the `SimpleChunk` model (`server/shared/models/simple_chunk.py`, already built). `elasticsearch` is
already a dependency (use the async client, `AsyncElasticsearch`). Read `RETRIEVAL.md` and the
"Re-ingestion archives" note in `INGESTION.md` — they define the exact filters and archival behavior.

## Goal

`server/shared/clients/search/client.py` — the only writer/reader of the `SimpleChunk` index.

## Spec

- **Field-name constants:** every ES field name is a module-level `SCREAMING_SNAKE` constant, reused by
  mapping, indexing, and query builders (one source of truth — `CLAUDE.local.md`).
- **`ensure_index()`** — create `settings.elasticsearch_index` (`roadbuilders_text`) if absent with a
  mapping: German analyzer on text; `dense_vector` (`dims = settings.embedding_dim`, similarity for
  kNN/HNSW) for `embedding`; BM25 on `chunk_text`; keyword fields for `project_uuid`, `source_doc_type`,
  `source_doc_uuid`, `oz`, `stl_nr`, plus `chunk_index`, `source_doc_field`, `source_doc_language`,
  `source_doc_pages`, `embedding_model`.
- **`index_chunks(chunks)`** — bulk index `SimpleChunk`s (assign `chunk_uuid` if using `NewSimpleChunk`).
- **Query builders honoring `RETRIEVAL.md`:** always filter `project_uuid == <scope>`, then:
  - **Simple:** `source_doc_type == DOCUMENT`.
  - **Plus:** `(DOCUMENT AND source_doc_uuid != <lv_document_uuid>) OR source_doc_type == LV_ITEM`
    (the caller passes the LV document uuid; there is exactly one per project).
  Provide a dense kNN query and a BM25 lexical query over the same filter. RRF fusion + cross-encoder
  rerank are the retrieval phase's concern, not this client.
- **`archive_source(source_doc_uuid, source_doc_type)`** — implement the re-ingestion archival from
  `INGESTION.md`: move all live chunks matching `(source_doc_uuid, source_doc_type)` to
  `f"{settings.elasticsearch_index}_archive"`, adding an `archived_at` timestamp, then delete them from
  the live index. Ensure the archive index exists.
- Re-export the client in `server/shared/clients/search/__init__.py`.

## Verification

`tests/integration/search/test_client.py` against the compose ES (8.15), **skipped if
`settings.elasticsearch_url` is unreachable**: `ensure_index` then index N chunks; dense kNN + BM25
return them under both Simple and Plus filters; `archive_source` moves a source's chunks to
`_archive` with `archived_at` and removes them from live. Bring up infra:
`docker compose up -d elasticsearch`.

## Done when

Index lifecycle + Simple/Plus queries + archival work against the compose ES and the gated integration
test passes (skips cleanly when ES is down).
