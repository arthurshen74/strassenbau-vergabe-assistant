-- 12_anzahl_st_variable.sql
-- Add the `anzahl_st` kontext geometry variable (Phase 3, D4): Mengeneinheit `St` joins the
-- engine geometry (GEOM["St"] = "anzahl_st"), so Stück-billed positions can book their LV menge
-- the same way m/m2/m3/t positions do. A fresh seed gets the row from the fixture
-- (kontext_variablen.py); this migration adds it to a DB seeded before Phase 3.
-- Idempotent: safe to re-run. Run after 11.
-- Run: psql -d roadbuilders -f sql/12_anzahl_st_variable.sql

INSERT INTO katalog_variablen (name, gruppe, bezeichnung, einheit, datentyp, aufloesung, version, status, benutzer)
SELECT 'anzahl_st', 'kontext', 'anzahl_st', 'St', 'dezimal',
       '[{"methode": "hitl", "prompt": null, "konfidenz_schwelle": null, "stammdaten_pfad": null, "formel_name": null, "konstante": null}]'::json,
       1, 'aktiv', 'seed'
WHERE NOT EXISTS (
    SELECT 1 FROM katalog_variablen WHERE name = 'anzahl_st' AND gruppe = 'kontext'
);
