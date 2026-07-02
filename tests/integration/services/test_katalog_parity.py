"""Integration form of the katalog parity harness (§10.2).

Seeds the catalog into a rolled-back transaction, loads it through the provider, and asserts the
refilled dicts and all 50 position calculations are byte-identical to the fixtures. `zustand_sichern`
restores the in-place-refilled module dicts so this test does not pollute later tests (e.g. one that
looks up `VORGAENGE["FRAESEN"]` by its fixture short-name key).
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncConnection

from shared.repositories.katalog import KatalogRepository

from scripts.check_katalog_parity import pruefe_parity, zustand_sichern
from scripts.seed.seed_katalog import seed_katalog


async def test_katalog_parity(conn: AsyncConnection) -> None:
    with zustand_sichern():
        repo = KatalogRepository(conn)
        await repo.alles_leeren()
        await seed_katalog(repo)
        fehler = await pruefe_parity(conn)
    assert not fehler, "Katalog-Parität verletzt:\n" + "\n".join(fehler)
