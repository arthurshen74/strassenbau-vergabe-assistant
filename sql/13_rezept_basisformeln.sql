-- 13_rezept_basisformeln.sql
-- Phase-2 DDL for the Rezept redesign (REZEPT_REDESIGN_PLAN §6/§7): base formulas carry a
-- declared parameter signature + prose; a Vorgang carries its Rechnung (base-formula
-- instantiations) instead of one formula name per Kostenart.
-- Additive only: the legacy columns (ergebnis_variable, leistung_variable, kostenvariablen)
-- stay on the superseded history rows and fall in the Phase-7 cleanup; new rows leave them
-- NULL. Historical rows get an empty parameter/rechnung backfill so the new NOT NULLs hold.
-- Idempotent: safe to re-run. Run after 12, BEFORE scripts.migrate_rezept_katalog.
-- Run: psql -d roadbuilders -f sql/13_rezept_basisformeln.sql

ALTER TABLE katalog_formeln ADD COLUMN IF NOT EXISTS beschreibung text;
ALTER TABLE katalog_formeln ADD COLUMN IF NOT EXISTS parameter json;
UPDATE katalog_formeln SET parameter = '[]'::json WHERE parameter IS NULL;
ALTER TABLE katalog_formeln ALTER COLUMN parameter SET NOT NULL;
ALTER TABLE katalog_formeln ALTER COLUMN ergebnis_variable DROP NOT NULL;

ALTER TABLE katalog_vorgaenge ADD COLUMN IF NOT EXISTS leistung_instanz text;
ALTER TABLE katalog_vorgaenge ADD COLUMN IF NOT EXISTS rechnung json;
UPDATE katalog_vorgaenge SET rechnung = '{"instanzen": {}, "kosten": {}}'::json WHERE rechnung IS NULL;
ALTER TABLE katalog_vorgaenge ALTER COLUMN rechnung SET NOT NULL;
ALTER TABLE katalog_vorgaenge ALTER COLUMN kostenvariablen DROP NOT NULL;
