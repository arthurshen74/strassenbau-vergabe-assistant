-- 18_multi_lv_documents.sql
-- A project may hold any number of LV documents (one per GAEB file, e.g. the same LV as
-- X83 and D83, or one LV per Los). Each keeps its own lv_items, lv_texts and ES chunks,
-- already keyed by document_uuid, so the only schema change is dropping the partial
-- unique index that allowed at most one LV_DOCUMENT per project. Mirrors
-- server/shared/db/tables/documents.py (the source of truth this file follows).
-- Idempotent: safe to re-run. Run after 17.
-- Run: psql -d roadbuilders -f sql/18_multi_lv_documents.sql

DROP INDEX IF EXISTS uq_one_lv_document_per_project;
