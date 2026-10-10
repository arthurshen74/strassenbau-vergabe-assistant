-- 22_rag_query_vergabestelle.sql
-- Widen the rag_query_versions query_key CHECK for 'project-vergabestelle' (fills
-- projects.vergabestelle). create_all(checkfirst) never alters an existing table, so seeding
-- the new query (scripts.seed.rag_queries) fails the CHECK until this runs. The value list
-- follows the ProjectInfoQuery enum. Idempotent: safe to re-run. Run after 21.
-- Run: psql -d roadbuilders -f sql/22_rag_query_vergabestelle.sql
-- Then seed: PYTHONPATH=server uv run python -m scripts.seed.rag_queries

ALTER TABLE rag_query_versions DROP CONSTRAINT IF EXISTS ck_rag_query_versions_query_key_valid;
ALTER TABLE rag_query_versions ADD CONSTRAINT ck_rag_query_versions_query_key_valid
    CHECK (query_key IN ('project-description', 'project-massnahmenummer', 'project-name',
                         'project-vergabenummer', 'project-bauleistung',
                         'project-location', 'project-vergabestelle'));
