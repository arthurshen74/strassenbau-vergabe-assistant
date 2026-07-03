"""Harness happy path (§8, criterion 6): describe → review → confirm+activate → calculable.

Drives the recipe-author graph with a mocked `entwerfer` (a fixed valid bundle) and the real
KatalogService seams, hits the rezept_review interrupt, resumes with confirm+activate, and asserts
the new Leistung is calculable through `kalkuliere` in the same test. Uses the session engine
(the service commits), so it seeds/cleans up explicitly and restores module dicts via
`zustand_sichern`.
"""

from __future__ import annotations

from decimal import Decimal

from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
from sqlalchemy.ext.asyncio import AsyncEngine

from shared.models.katalog import (
    BundleBauverfahren,
    BundleVorgang,
    KatalogBundle,
)
from shared.repositories.katalog import KatalogRepository
from shared.services.kalkulation_v2.model import Formel, Kostenart, Leistung
from shared.services.kalkulation_v2.positionen import Position
from shared.services.kalkulation_v2.store import kalkuliere
from shared.services.katalog.service import KatalogService
from shared.services.rezept_autor.graph import STAGE_REZEPT_REVIEW, build_graph

from scripts.check_katalog_parity import zustand_sichern
from scripts.seed.seed_katalog import seed_katalog

INTERRUPT_KEY = "__interrupt__"


def _fixed_bundle() -> KatalogBundle:
    return KatalogBundle(
        leistungen=[Leistung(code="L_AUTOR_TEST", name="Autor-Teststrecke", einheit="m2")],
        formeln=[
            Formel(name="mk_autor_test", ergebnis_variable="mk_autor_test", ausdruck="flaeche_m2 * 7", einheit="€")
        ],
        vorgaenge=[
            BundleVorgang(code="V_AUTOR_TEST", name="Autor-Testvorgang", kostenvariablen={Kostenart.MASCHINE: "mk_autor_test"})
        ],
        bauverfahren=[BundleBauverfahren(code="BV_AUTOR_TEST", name="Autor-Testverfahren", vorgang_codes=["V_AUTOR_TEST"])],
        leistung_bauverfahren={"L_AUTOR_TEST": ["BV_AUTOR_TEST"]},
    )


async def test_harness_beschreiben_pruefen_bestaetigen_aktivieren(engine: AsyncEngine) -> None:
    with zustand_sichern():
        async with engine.begin() as conn:
            repo = KatalogRepository(conn)
            await repo.alles_leeren()
            await seed_katalog(repo)
        try:
            service = KatalogService(engine)

            async def entwerfer(_beschreibung, _fehler, _feedback):
                return _fixed_bundle()

            graph = build_graph(
                entwerfer=entwerfer,
                pruefer=service.pruefen,
                speichern=lambda b: service.entwurf_speichern(b, benutzer="autor-test"),
                aktivieren=service.bundle_aktivieren,
                checkpointer=MemorySaver(),
            )
            config = {"configurable": {"thread_id": "rezept-autor-test"}}

            # describe -> validate -> review interrupt
            interrupts = []
            async for chunk in graph.astream(
                {"beschreibung": "Neue Teststrecke, Kosten aus der Fläche."}, config, stream_mode="updates"
            ):
                if INTERRUPT_KEY in chunk:
                    interrupts.append(chunk[INTERRUPT_KEY][0].value)
            assert len(interrupts) == 1
            review = interrupts[0]
            assert review["stage"] == STAGE_REZEPT_REVIEW
            assert review["bericht"]["fehler"] == []

            # confirm + activate
            async for _chunk in graph.astream(
                Command(resume={"bestaetigt": True, "feedback": None, "aktivieren": True}),
                config,
                stream_mode="updates",
            ):
                pass
            final = (await graph.aget_state(config)).values
            assert final["gespeichert"] is True
            assert final["aktiviert"] is True

            # the new Leistung is calculable through the reloaded engine
            ergebnis = kalkuliere(Position(oz="AUTOR-01", leistung_key="L_AUTOR_TEST", menge=Decimal("100")))
            assert ergebnis["bauverfahren"] == "BV_AUTOR_TEST"
            assert ergebnis["ekt_eur"] == Decimal("700.00")
            assert ergebnis["ep_eur"] == Decimal("7.00")
        finally:
            async with engine.begin() as conn:
                await KatalogRepository(conn).alles_leeren()
