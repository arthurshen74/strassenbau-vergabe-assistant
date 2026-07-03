"""The write-boundary facade for the catalog agent (§8, D8).

`KatalogEntwurfDienst` is the ONLY write surface the agent's write tools touch. It exposes exactly
three write operations — validate, save-draft, discard — and deliberately NOT `bundle_aktivieren`:
activation is a human decision made on the confirm card through the API route, never reachable from
a tool. This is the HITL boundary made structural, not prompt-enforced (the import-graph test in
`test_katalog_readonly.py` asserts the tool/agent/facade modules never reference `bundle_aktivieren`).

It also carries the small read helpers a write tool needs to *build* a proposal — the current active
payload behind an `aendere_*` delta, the open-ended price a new price would close out, and a
variable's where-used blast radius — so the tools go through one object. All reads are `aktiv`-only.
"""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncEngine

from shared.models.katalog import (
    BundleBericht,
    KatalogBundle,
    KatalogEntitaet,
    KatalogPreis,
    KatalogZeile,
)
from shared.repositories.katalog import KATALOG_REGISTRY, KatalogRepository
from shared.services.katalog.lese_modell import LeseModell
from shared.services.katalog.service import DEFAULT_AUTOR, KatalogService

__all__ = ["DEFAULT_AUTOR", "KatalogEntwurfDienst"]


class KatalogEntwurfDienst:
    """Validate / save-draft / discard a KatalogBundle, plus the reads a proposal is built from."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine
        self._service = KatalogService(engine)

    # --- the write boundary (no activation) -------------------------------------------------- #

    async def pruefen(self, bundle: KatalogBundle) -> BundleBericht:
        """Validate a bundle against the active catalog without writing."""
        return await self._service.pruefen(bundle)

    async def entwurf_speichern(self, bundle: KatalogBundle, benutzer: str) -> UUID:
        """Validate, then persist the bundle as drafts sharing one bundle_uuid. Raises
        `BundleUngueltig` on a validation failure (nothing is written)."""
        return await self._service.entwurf_speichern(bundle, benutzer)

    async def bundle_verwerfen(self, bundle_uuid: UUID, benutzer: str = DEFAULT_AUTOR) -> None:
        """Discard a draft bundle (rows → verworfen). Raises `BundleNichtGefunden` if it has no
        open drafts. Never touches the active catalog."""
        await self._service.bundle_verwerfen(bundle_uuid, benutzer=benutzer)

    # --- reads a write tool needs to build a proposal ---------------------------------------- #

    async def aktive_zeile(
        self, entitaet: KatalogEntitaet, schluessel: str, gruppe: str | None = None
    ) -> KatalogZeile | None:
        """The active row for a natural key (optionally disambiguated by the variablen gruppe
        discriminator), or None. The delta base + diff source for the `aendere_*` tools."""
        spec = KATALOG_REGISTRY[entitaet]
        async with self._engine.connect() as conn:
            for z in await KatalogRepository(conn).aktive(entitaet):
                if z.schluessel != schluessel:
                    continue
                if gruppe is not None and spec.diskriminator is not None:
                    if z.payload.get(spec.diskriminator) != gruppe:
                        continue
                return z
        return None

    async def preis_vorgaenger_offen(
        self, lieferant_code: str, baustoff_code: str, gueltig_ab: date
    ) -> KatalogPreis | None:
        """The open-ended active price a new price starting at `gueltig_ab` would close out (D5)."""
        async with self._engine.connect() as conn:
            return await KatalogRepository(conn).preis_vorgaenger_offen(
                lieferant_code, baustoff_code, gueltig_ab
            )

    async def verwendung_von_variable(self, name: str) -> dict[str, Any]:
        """The T30 where-used envelope — the blast radius shown on a rate-change card (W11)."""
        async with self._engine.connect() as conn:
            return await LeseModell(conn).verwendung_von_variable(name)

    async def suche(
        self, text: str, entitaeten: list[str], limit: int | None = None
    ) -> list[dict[str, Any]]:
        """Ranked BM25 hits over the active catalog — the W18 near-duplicate probe."""
        async with self._engine.connect() as conn:
            env = await LeseModell(conn).suche_katalog(text, entitaeten=entitaeten, limit=limit)
        return env["eintraege"]

    async def aktive_formeln_und_vorgaenge(self) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
        """Active Formeln (by name) and Vorgang payloads (by code) — the W18 geometry walk's view
        of what a reused chain member transitively depends on."""
        async with self._engine.connect() as conn:
            repo = KatalogRepository(conn)
            formeln = {z.schluessel: z.payload for z in await repo.aktive(KatalogEntitaet.FORMELN)}
            vorgaenge = {z.schluessel: z.payload for z in await repo.aktive(KatalogEntitaet.VORGAENGE)}
        return formeln, vorgaenge

    async def aktive_preise(self) -> list[KatalogPreis]:
        """All active supplier price rows (used to render a supplier's assortment on a card)."""
        async with self._engine.connect() as conn:
            return await KatalogRepository(conn).preise()
