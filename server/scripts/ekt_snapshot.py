"""EKT parity snapshot: freeze cent-exact results of the CURRENT engine + catalog.

Run BEFORE the formula redesign (and again after, with --vergleich) to prove the new
engine
reproduces every EKT to the cent (REZEPT_REDESIGN_PLAN.md §6). Three coverage sets:

1. POSITIONEN — the 41-row L-101 fixture worklist, computed on the DB-loaded catalog.
2. Synthetic — every active Leistung with a Bauverfahren mapping, menge=100, a fixed
generic
   kontext and a deterministic Baustoff pick; positions whose worklist cannot be
   satisfied are
   recorded as unresolvable (the new engine must fail on exactly the same set).

Read-only: `lade_katalog` only reads. Results land in eval/parity/ekt_snapshot.json.
"""

from __future__ import annotations

import asyncio
import json
import sys
from decimal import Decimal
from pathlib import Path

from sqlalchemy.ext.asyncio import create_async_engine

import shared.db.tables  # noqa: F401
from shared.config import settings
from shared.services.kalkulation_v2 import bauverfahren as m_bv
from shared.services.kalkulation_v2 import leistung_bauverfahren as m_lb
from shared.services.kalkulation_v2 import leistungen as m_leist
from shared.services.kalkulation_v2 import materialien as m_mat
from shared.services.kalkulation_v2.positionen import Position
from shared.services.kalkulation_v2.provider import lade_katalog
from shared.services.kalkulation_v2.store import POSITIONEN, kalkuliere

SNAPSHOT_PFAD = (
    Path(__file__).resolve().parents[2] / "eval" / "parity" / "ekt_snapshot.json"
)

# Generic kontext for synthetic coverage — superset of the Gate-B eval answers plus
# every
# EINGABE leaf the fixture recipes know. Values are arbitrary but FROZEN: parity
# compares
# old vs new engine on identical inputs, realism is irrelevant.
SYNTH_KONTEXT: dict[str, str] = {
    "tiefe_cm": "5",
    "einbaudicke_cm": "4",
    "schichtdicke_m": "0.30",
    "ev2_ziel": "70",
    "anzahl_arbeiter": "3",
    "erschwernisfaktor": "1.0",
    "fraesgut_klasse": "1",
    "entfernung_lieferant_km": "15",
    "entfernung_deponie_km": "15",
    "materialpreis_eur_pro_t": "20.00",
    "naht_dicke_cm": "10",
    "fugenspalttiefe_mm": "25",
    "fugenspaltbreite_mm": "10",
    "bindemittelmenge_kg_pro_m2": "0.30",
    "abstreumenge_kg_pro_m2": "1.0",
    "markierung_leistung_m_pro_h": "100",
    "anzahl_st": "8",
}


def _baustoff_fuer(bv_code: str) -> str | None:
    """Deterministic Baustoff pick: first code (sorted) whose Kategorie the recipe name
    hints at,
    else the first Baustoff overall. Arbitrary but frozen."""
    codes = sorted(m_mat.BAUSTOFFE)
    return codes[0] if codes else None


def _sicher_kalkulieren(pos: Position) -> dict:
    try:
        r = kalkuliere(pos)
        return {
            "ok": True,
            "bauverfahren": r["bauverfahren"],
            "einheit": r["einheit"],
            "ekt_eur": str(r["ekt_eur"]),
            "ep_eur": str(r["ep_eur"]),
            "linien": [
                {
                    "vorgang": d["vorgang"],
                    "positionen": [
                        {
                            "kostenart": p["kostenart"],
                            "betrag_eur": str(p["betrag_eur"]),
                        }
                        for p in d["positionen"]
                    ],
                }
                for d in r["detail"]
            ],
        }
    except Exception as e:  # noqa: BLE001 — unresolvable positions are part of the snapshot
        return {"ok": False, "fehler": f"{type(e).__name__}: {e}"}


async def main() -> None:
    engine = create_async_engine(settings.database_url)
    try:
        async with engine.connect() as conn:
            geladen = await lade_katalog(conn)
    finally:
        await engine.dispose()
    if geladen is None:
        print("Katalog-Tabellen leer — Snapshot abgebrochen.")
        raise SystemExit(1)

    snapshot: dict = {
        "katalog_stand": geladen.get("stand"),
        "positionen": {},
        "synthetisch": {},
    }

    for pos in POSITIONEN:
        snapshot["positionen"][pos.oz] = _sicher_kalkulieren(pos)

    for l_key in sorted(m_lb.LEISTUNG_BAUVERFAHREN):
        if l_key not in m_leist.LEISTUNGEN:
            continue
        for bv_key in m_lb.LEISTUNG_BAUVERFAHREN[l_key]:
            if bv_key not in m_bv.BAUVERFAHREN:
                continue
            kontext = {k: Decimal(v) for k, v in SYNTH_KONTEXT.items()}
            pos = Position(
                oz=f"SYN::{l_key}::{bv_key}",
                leistung_key=l_key,
                menge=Decimal("100"),
                bauverfahren_key=bv_key,
                baustoff_code=_baustoff_fuer(bv_key),
                kontext=kontext,
            )
            snapshot["synthetisch"][pos.oz] = _sicher_kalkulieren(pos)

    if "--vergleich" in sys.argv:
        alt = json.loads(SNAPSHOT_PFAD.read_text())
        fehler: list[str] = []
        for gruppe in ("positionen", "synthetisch"):
            for oz, alt_r in alt[gruppe].items():
                neu_r = snapshot[gruppe].get(oz)
                if neu_r != alt_r:
                    neu_wert = (
                        None
                        if neu_r is None
                        else neu_r.get("ekt_eur", neu_r.get("fehler"))
                    )
                    fehler.append(
                        f"{oz}: alt={alt_r.get('ekt_eur', alt_r.get('fehler'))} "
                        f"neu={neu_wert}"
                    )
        if fehler:
            print(f"PARITY FAILED — {len(fehler)} Abweichung(en):")
            for f in fehler[:40]:
                print(f"  {f}")
            raise SystemExit(1)
        n = len(alt["positionen"]) + len(alt["synthetisch"])
        print(f"PARITY OK — {n} Positionen cent-identisch.")
        return

    SNAPSHOT_PFAD.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_PFAD.write_text(json.dumps(snapshot, indent=1, ensure_ascii=False))
    ok = sum(
        1
        for g in ("positionen", "synthetisch")
        for r in snapshot[g].values()
        if r["ok"]
    )
    gesamt = len(snapshot["positionen"]) + len(snapshot["synthetisch"])
    print(
        f"Snapshot geschrieben: {SNAPSHOT_PFAD} — {ok}/{gesamt} Positionen berechnet "
        f"(Katalog-Stand {snapshot['katalog_stand']})."
    )


if __name__ == "__main__":
    asyncio.run(main())
