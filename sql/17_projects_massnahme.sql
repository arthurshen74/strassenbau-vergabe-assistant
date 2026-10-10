-- 17_projects_massnahme.sql
-- Project header fields for the ZIP-first creation flow: a project is created from its tender
-- ZIP with only a name, and the header is filled in after ingestion (RAG extraction or by hand).
--   massnahmenummer  the Maßnahmenummer (project_name already holds the Maßnahme)
--   bauleistung      the contract name (Bauleistung)
-- vergabe_id (Vergabenummer), vergabestelle and project_description lose NOT NULL because they
-- are unknown at creation time. project_name stays NOT NULL. Mirrors
-- server/shared/db/tables/projects.py (the source of truth this file follows).
-- Idempotent: safe to re-run. Run after 16.
-- Run: psql -d roadbuilders -f sql/17_projects_massnahme.sql

ALTER TABLE projects ADD COLUMN IF NOT EXISTS massnahmenummer text;
ALTER TABLE projects ADD COLUMN IF NOT EXISTS bauleistung text;

ALTER TABLE projects ALTER COLUMN vergabe_id DROP NOT NULL;
ALTER TABLE projects ALTER COLUMN vergabestelle DROP NOT NULL;
ALTER TABLE projects ALTER COLUMN project_description DROP NOT NULL;
