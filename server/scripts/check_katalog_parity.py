"""Parity harness: prove the DB-backed catalog is identical to the fixtures.

Two checks, both must hold (acceptance criterion §10.2):

1. Dict parity — after `lade_katalog`, every refilled catalog dict deep-equals its
fixture
   (compared as `model_dump(mode="json")` keyed by domain identity, so the incidental
   short-name keys of Ausführungsarten/Vorgänge and the storage order of a supplier's
   prices don't matter; the Step-0 prefactor already removed the ephemeral `id` fields,
   so nothing is excluded).
2. Calculation parity — `kalkuliere(pos)` for every `POSITIONEN` position yields
byte-identical
   EKT/EP on the fixture catalog and the DB catalog.

Ships as this script (`uv run python -m scripts.check_katalog_parity`, non-destructive:
seeds a rolled-back transaction on the test DB) and as an integration test.
`zustand_sichern` restores the in-place-refilled module dicts afterward so the
in-process test does not pollute later tests.
"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from typing import Any, Callable, Iterator

from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

import shared.db.tables  # noqa: F401  -- registers tables on the shared metadata
from shared.config import settings
from shared.db.metadata import metadata
from shared.repositories.katalog import KatalogRepository
from shared.services.kalkulation_v2 import ausfuehrungsarten as m_aa
from shared.services.kalkulation_v2 import baustoff_suche as m_bs
from shared.services.kalkulation_v2 import bauverfahren as m_bv
from shared.services.kalkulation_v2 import betriebsarten as m_bt
from shared.services.kalkulation_v2 import formel as m_formel
from shared.services.kalkulation_v2 import globale_variablen as m_glob
from shared.services.kalkulation_v2 import kontext_variablen as m_kontext
from shared.services.kalkulation_v2 import leistung_bauverfahren as m_lb
from shared.services.kalkulation_v2 import leistungen as m_leist
from shared.services.kalkulation_v2 import lieferanten as m_lief
from shared.services.kalkulation_v2 import maschinen as m_masch
from shared.services.kalkulation_v2 import materialien as m_mat
from shared.services.kalkulation_v2 import stammdaten as m_stamm
from shared.services.kalkulation_v2 import store as m_store
from shared.services.kalkulation_v2 import vorgaenge as m_vorg
from shared.services.kalkulation_v2.provider import lade_katalog
from shared.services.kalkulation_v2.store import POSITIONEN, kalkuliere

from scripts.seed.seed_katalog import seed_katalog

# (snapshot label, live dict, identity-of-a-value) for the model dicts compared
# field-for-field.
_MODEL_DICTS: list[tuple[str, dict, Callable[[Any], str]]] = [
    ("BETRIEBSKATEGORIEN", m_bt.BETRIEBSKATEGORIEN, lambda m: m.code),
    ("BETRIEBSARTEN", m_bt.BETRIEBSARTEN, lambda m: m.code),
    ("AUSFUEHRUNGSARTEN", m_aa.AUSFUEHRUNGSARTEN, lambda m: m.code),
    ("FORMELN", m_formel.FORMELN, lambda m: m.name),
    ("STAMMDATEN_VARIABLEN", m_stamm.STAMMDATEN_VARIABLEN, lambda m: m.name),
    ("KONTEXT_VARIABLEN", m_kontext.KONTEXT_VARIABLEN, lambda m: m.name),
    ("BAUSTOFFE", m_mat.BAUSTOFFE, lambda m: m.code),
    ("MASCHINEN", m_masch.MASCHINEN, lambda m: m.code),
    ("VORGAENGE", m_vorg.VORGAENGE, lambda m: m.code),
    ("BAUVERFAHREN", m_bv.BAUVERFAHREN, lambda m: m.code),
    ("LEISTUNGEN", m_leist.LEISTUNGEN, lambda m: m.code),
    ("GLOBALE_VARIABLEN", m_glob.GLOBALE_VARIABLEN, lambda m: m.name),
    ("KATALOG", m_store.KATALOG, lambda m: m.name),
]

# Every module-level container `lade_katalog` mutates in place — saved and restored by
# the test.
_MUTABLE: list[Any] = [d for _, d, _ in _MODEL_DICTS] + [
    m_lief.LIEFERANTEN,
    m_lb.LEISTUNG_BAUVERFAHREN,
    m_glob.GLOBAL_VAR_NAMES,
    m_glob.ERFORDERLICHE_GLOBALE,
]


def _lieferant_dump(lief: Any) -> dict:
    d = lief.model_dump(mode="json")
    d["preise"] = sorted(
        d["preise"],
        key=lambda p: (p["baustoff_code"], p["gueltig_ab"], p["gueltig_bis"] or ""),
    )
    return d


def _snapshot() -> dict[str, dict]:
    """Identity-keyed `model_dump(mode="json")` of every catalog dict
    (order-normalized)."""
    snap: dict[str, dict] = {}
    for name, d, ident in _MODEL_DICTS:
        snap[name] = {ident(m): m.model_dump(mode="json") for m in d.values()}
    snap["LIEFERANTEN"] = {
        lief.code: _lieferant_dump(lief) for lief in m_lief.LIEFERANTEN.values()
    }
    snap["LEISTUNG_BAUVERFAHREN"] = {
        k: list(v) for k, v in m_lb.LEISTUNG_BAUVERFAHREN.items()
    }
    return snap


def _calc_all() -> dict[str, dict]:
    return {pos.oz: kalkuliere(pos) for pos in POSITIONEN}


def _dict_differenzen(name: str, ref: dict, other: dict) -> list[str]:
    fehler: list[str] = []
    fehlend = set(ref) - set(other)
    zuviel = set(other) - set(ref)
    if fehlend:
        fehler.append(f"{name}: fehlend nach Reload: {sorted(fehlend)[:5]}")
    if zuviel:
        fehler.append(f"{name}: zusätzlich nach Reload: {sorted(zuviel)[:5]}")
    for key in sorted(set(ref) & set(other)):
        if ref[key] != other[key]:
            fehler.append(
                f"{name}[{key}] weicht ab: fixture={ref[key]!r} db={other[key]!r}"
            )
            if len(fehler) >= 5:
                break
    return fehler


@contextmanager
def zustand_sichern() -> Iterator[None]:
    """Snapshot every module dict/set `lade_katalog` mutates and restore them on exit,
    so an in-process parity check does not leave the engine's catalog dicts
    refilled/re-keyed."""
    gesichert = [(obj, obj.copy()) for obj in _MUTABLE]
    try:
        yield
    finally:
        for obj, original in gesichert:
            obj.clear()
            obj.update(original)
        m_bs.baue_index()


async def pruefe_parity(conn: AsyncConnection) -> list[str]:
    """Load the seeded catalog on `conn` and return parity failures (empty ⇒ parity
    holds).

    Assumes the katalog tables on `conn` are already seeded. Snapshots the fixtures and
    computes fixture EKT/EP BEFORE `lade_katalog` refills the dicts in place, then
    compares against the DB-backed state.
    """
    referenz = _snapshot()
    fixture_ergebnisse = _calc_all()

    await lade_katalog(conn)

    geladen = _snapshot()
    db_ergebnisse = _calc_all()

    fehler: list[str] = []
    for name in referenz:
        fehler.extend(_dict_differenzen(name, referenz[name], geladen[name]))
    for oz, fixture_r in fixture_ergebnisse.items():
        if fixture_r != db_ergebnisse[oz]:
            fehler.append(
                f"calc {oz}: EKT fixture={fixture_r['ekt_eur']} "
                f"db={db_ergebnisse[oz]['ekt_eur']} "
                f"/ EP fixture={fixture_r['ep_eur']} db={db_ergebnisse[oz]['ep_eur']}"
            )
    return fehler


async def main() -> None:
    engine = create_async_engine(settings.test_database_url)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(metadata.create_all)
        async with engine.connect() as conn:
            trans = await conn.begin()
            try:
                repo = KatalogRepository(conn)
                await repo.alles_leeren()
                await seed_katalog(repo)
                fehler = await pruefe_parity(conn)
            finally:
                await trans.rollback()
    finally:
        await engine.dispose()

    if fehler:
        print(f"PARITY FAILED — {len(fehler)} Abweichung(en):")
        for f in fehler:
            print(f"  {f}")
        raise SystemExit(1)
    print(
        f"PARITY OK — {len(_MODEL_DICTS) + 2} Kataloge und {len(POSITIONEN)} "
        f"Positionen identisch."
    )


if __name__ == "__main__":
    asyncio.run(main())
