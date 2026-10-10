-- 24_form_documents.sql
-- Form documents (Formblätter): a third document type FORM_DOCUMENT with the form's role
-- (vergabestelle / bieter / unbekannt) and Formblatt id on documents, the skipped ingest
-- status for Bieter forms (on ingest_jobs and project_info_jobs, both built from
-- IngestStatus), and form_fields, the structured label/value rows extracted from a form.
-- Mirrors server/shared/db/tables/documents.py, ingest_jobs.py, project_info_jobs.py and
-- form_fields.py (the source of truth this file follows).
-- Idempotent: safe to re-run. Run after 23.
-- Run: psql -d roadbuilders -f sql/24_form_documents.sql

ALTER TABLE documents ADD COLUMN IF NOT EXISTS form_role TEXT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS form_id TEXT;

ALTER TABLE documents DROP CONSTRAINT IF EXISTS ck_documents_document_type_valid;
ALTER TABLE documents ADD CONSTRAINT ck_documents_document_type_valid
	CHECK (document_type IN ('LV_DOCUMENT', 'PROSE_DOCUMENT', 'FORM_DOCUMENT'));

ALTER TABLE documents DROP CONSTRAINT IF EXISTS ck_documents_form_role_valid;
ALTER TABLE documents ADD CONSTRAINT ck_documents_form_role_valid
	CHECK (form_role IN ('vergabestelle', 'bieter', 'unbekannt'));

ALTER TABLE documents DROP CONSTRAINT IF EXISTS ck_documents_document_type_form_role;
ALTER TABLE documents ADD CONSTRAINT ck_documents_document_type_form_role
	CHECK ((document_type = 'FORM_DOCUMENT') = (form_role IS NOT NULL));

ALTER TABLE ingest_jobs DROP CONSTRAINT IF EXISTS ck_ingest_jobs_status_valid;
ALTER TABLE ingest_jobs ADD CONSTRAINT ck_ingest_jobs_status_valid
	CHECK (status IN ('queued', 'running', 'done', 'failed', 'skipped'));

ALTER TABLE project_info_jobs DROP CONSTRAINT IF EXISTS ck_project_info_jobs_status_valid;
ALTER TABLE project_info_jobs ADD CONSTRAINT ck_project_info_jobs_status_valid
	CHECK (status IN ('queued', 'running', 'done', 'failed', 'skipped'));

CREATE TABLE IF NOT EXISTS form_fields (
	document_uuid UUID NOT NULL,
	field_order INTEGER NOT NULL,
	section TEXT NOT NULL,
	name TEXT NOT NULL,
	label TEXT,
	value TEXT NOT NULL,
	page INTEGER NOT NULL,
	CONSTRAINT pk_form_fields PRIMARY KEY (document_uuid, field_order),
	CONSTRAINT fk_form_fields_document_uuid_documents FOREIGN KEY(document_uuid) REFERENCES documents (document_uuid) ON DELETE CASCADE
);
