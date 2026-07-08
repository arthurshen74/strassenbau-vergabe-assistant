"""End-to-end integration (§10.5): a rate change flows through the whole write path.

The W11 tool drafts a KONSTANTE-rate change → the confirm card sees `offen` → activation through the
service (what the endpoint calls) reloads the provider → `kalkuliere` uses the new rate. The discard
path leaves the running engine untouched. Uses the session engine, so it seeds/cleans explicitly and
restores the in-place-refilled module dicts via `zustand_sichern`.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from langchain_core.tools import BaseTool
from sqlalchemy.ext.asyncio import AsyncEngine

from shared.models.katalog import (
    BundleBauverfahren,
    BundleVariable,
    BundleVorgang,
    BundleZustand,
    KatalogBundle,
    VariablenGruppe,
)
from shared.repositories.katalog import KatalogRepository
from shared.services.kalkulation_v2.model import (
    AufloesungsMethode,
    AufloesungsSchritt,
    D,
    FormelInstanz,
    Kostenart,
    Leistung,
    VariableDefinition,
    VorgangRechnung,
)
from shared.services.kalkulation_v2.positionen import Position
from shared.services.kalkulation_v2.store import kalkuliere
from shared.services.katalog.service import KatalogService
from shared.services.katalog.werkzeuge_schreiben import katalog_schreib_werkzeuge

from scripts.check_katalog_parity import zustand_sichern
from scripts.seed.seed_katalog import seed_katalog


def _e2e_rezept() -> KatalogBundle:
    """A self-contained Leistung whose Maschine cost line instantiates F_KOSTEN_SATZ as
    `flaeche_m2 × e2e_rate_eur` — the satz is a STAMMDATEN KONSTANTE the W11 tool later changes."""
    return KatalogBundle(
        leistungen=[Leistung(code="L_E2E", name="E2E-Teststrecke", einheit="m2")],
        variablen=[
            BundleVariable(
                gruppe=VariablenGruppe.STAMMDATEN,
                definition=VariableDefinition(
                    name="e2e_rate_eur", bezeichnung="E2E-Satz",
                    beschreibung="End-to-End-Testsatz je m²; speist den satz-Parameter der "
                                 "F_KOSTEN_SATZ-Materialzeile des Testvorgangs.",
                    einheit="€",
                    aufloesung=[
                        AufloesungsSchritt(methode=AufloesungsMethode.KONSTANTE, konstante=D("5"))
                    ],
                ),
            )
        ],
        vorgaenge=[
            BundleVorgang(
                code="V_E2E",
                name="E2E-Vorgang",
                rechnung=VorgangRechnung(
                    kosten={
                        Kostenart.MASCHINE: [
                            FormelInstanz(
                                formel="F_KOSTEN_SATZ",
                                bindung={"menge": "kontext.flaeche_m2", "satz": "stammdaten.e2e_rate_eur"},
                            )
                        ]
                    }
                ),
            )
        ],
        bauverfahren=[BundleBauverfahren(code="BV_E2E", name="E2E-Verfahren", vorgang_codes=["V_E2E"])],
        leistung_bauverfahren={"L_E2E": ["BV_E2E"]},
    )


async def _call(tools: dict[str, BaseTool], werkzeug: str, /, **args: Any) -> dict[str, Any]:
    msg = await tools[werkzeug].ainvoke(
        {"type": "tool_call", "name": werkzeug, "args": args, "id": "c"}
    )
    return msg.artifact  # type: ignore[attr-defined]


def _ekt(menge: int) -> Decimal:
    return kalkuliere(Position(oz="E2E", leistung_key="L_E2E", menge=Decimal(menge)))["ekt_eur"]


async def test_w11_ratenaenderung_bis_kalkulation(engine: AsyncEngine) -> None:
    with zustand_sichern():
        async with engine.begin() as conn:
            repo = KatalogRepository(conn)
            await repo.alles_leeren()
            await seed_katalog(repo)
        try:
            service = KatalogService(engine)
            tools = {t.name: t for t in katalog_schreib_werkzeuge(engine)}

            # Activate the recipe; at rate 5, 100 m² costs 500 €.
            await service.bundle_aktivieren(await service.entwurf_speichern(_e2e_rezept(), benutzer="t"))
            assert _ekt(100) == Decimal("500.00")

            # W11: draft the rate change → card sees it open → activate → engine reloads.
            art = await _call(tools, "aendere_stammdaten_wert", name="e2e_rate_eur", wert=7.0)
            assert art["bundle_uuid"] and art["diff"][0]["neu"] == "7"
            zustand = await service.bundle_zustand(UUID(art["bundle_uuid"]))
            assert zustand.zustand == BundleZustand.OFFEN
            await service.bundle_aktivieren(UUID(art["bundle_uuid"]))
            assert _ekt(100) == Decimal("700.00")  # the calculation uses the new rate

            # Discard path: a further draft, then discarded, must NOT touch the running engine.
            weg = await _call(tools, "aendere_stammdaten_wert", name="e2e_rate_eur", wert=999.0)
            await service.bundle_verwerfen(UUID(weg["bundle_uuid"]))
            assert _ekt(100) == Decimal("700.00")  # unchanged — discard reloaded nothing
        finally:
            async with engine.begin() as conn:
                await KatalogRepository(conn).alles_leeren()
