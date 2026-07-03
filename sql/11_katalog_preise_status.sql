-- 11_katalog_preise_status.sql
-- Add the price lifecycle columns to katalog_lieferanten_preise (Phase 2, D5): a price now rides
-- the draft->confirm flow via a `status` (entwurf|aktiv|archiviert), tagged with the `bundle_uuid`
-- it was proposed in and the `benutzer` who proposed it. The price VALUE stays immutable and
-- unversioned -- only the status column is new machinery.
--
-- create_all(checkfirst) never ALTERs an existing table, so these columns must be added here for a
-- DB that already has the table. A fresh create_all builds `status` as NOT NULL with no default;
-- this migration populates existing rows to 'aktiv' first, then sets NOT NULL and drops the
-- transient default, so a migrated DB's schema matches a fresh one exactly (no lingering column
-- default). Idempotent: safe to re-run. Run after 10.
-- Run: psql -d roadbuilders -f sql/11_katalog_preise_status.sql

ALTER TABLE katalog_lieferanten_preise ADD COLUMN IF NOT EXISTS status text;
ALTER TABLE katalog_lieferanten_preise ADD COLUMN IF NOT EXISTS bundle_uuid uuid;
ALTER TABLE katalog_lieferanten_preise ADD COLUMN IF NOT EXISTS benutzer text;

-- Existing rows are the active catalog.
UPDATE katalog_lieferanten_preise SET status = 'aktiv' WHERE status IS NULL;

ALTER TABLE katalog_lieferanten_preise ALTER COLUMN status SET NOT NULL;
