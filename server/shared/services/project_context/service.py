"""Resolve, persist and project the project-scoped context globals.

`resolve` fills in every global not yet present: hybrid retrieval finds the chunks, the
dedicated `PROJECT_CONTEXT_RESOLVE` synthesis distills the value, locations are geocoded, and
each is written as a new RAG version; `entfernung_deponie_km` is then derived by routing.
`save` applies a user override (geocoding changed locations, recomputing the deponie distance)
as new HITL versions. `current_read`/`history` project the version rows for the API/UI.

The service is constructed with an `AsyncConnection` (the GroundTruthService idiom): a
transactional connection for the writing paths (`resolve`, `save`) and a read connection for
the projecting paths. It owns no graph dependency; the retrieval policy is mirrored locally.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

from shared.clients.llm.client import LLMClient
from shared.clients.maps import Koordinate, MapsError, geocode, road_distance_km
from shared.config import settings
from shared.models.enums import ContextQuelle, ContextStatus, RetrievalModality
from shared.models.project_context import NewProjectContextValue, ProjectContextValue
from shared.models.prompt_version import PromptVersion
from shared.models.project_context_schema import (
    ProjectContextHistory,
    ProjectContextRead,
    ProjectContextUpdate,
)
from shared.repositories.project_context_values import ProjectContextValueRepository
from shared.services.kalkulation_v2.globale_variablen import (
    GLOBALE_VARIABLEN,
    VAR_BAUSTELLE_LOCATION,
    VAR_DEPONIE_LOCATION,
    VAR_ENTFERNUNG_DEPONIE_KM,
    VAR_FRAESGUT_KLASSE,
    VAR_STRIP_LENGTH_M,
    VAR_STRIP_WIDTH_M,
    GlobaleVariable,
)
from shared.services.project_context.llm import resolve_globale
from shared.services.retrieval import RetrievalService
from shared.services.retrieval.config import RetrievalConfig
from shared.services.retrieval.models import RetrievalContext

# Mirrors the calculator's hybrid policy (graph.CALCULATOR_RETRIEVAL_CONFIG): the resolver owns
# its own instance so this module never imports the heavy calculator graph.
RESOLVE_RETRIEVAL_CONFIG = RetrievalConfig(
    modality=RetrievalModality.PLUS,
    multi_query=True,
    use_bm25=True,
    use_cross_encoder=True,
)

# A geocoded location below this confidence is flagged UNSICHER (matches graph.GEOCODE_HITL_THRESHOLD).
GEOCODE_UNSICHER_SCHWELLE = 0.6

ROUTING_PROVIDER = "google_routes"

# Governance user placeholder until fastapi-users lands (PROJECT_CONTEXT_PLAN §11.1): every
# `benutzer` write references this one constant. When auth lands, the caller threads the real
# authenticated user into `save` instead.
DEFAULT_USER = "DEFAULT_USER"

# Offline fixtures (settings.calculator_mock): the resolver skips retrieval + LLM. The mock
# geocoder returns a fixed coordinate for any address, so the deponie distance resolves to ~0.
_MOCK_WERTE: dict[str, str] = {
    VAR_BAUSTELLE_LOCATION: "Baustelle L 101, Nordhausen",
    VAR_DEPONIE_LOCATION: "Deponie Sangerhausen",
    VAR_STRIP_LENGTH_M: "5100",
    VAR_STRIP_WIDTH_M: "1.0",
    VAR_FRAESGUT_KLASSE: "1",
}


class ProjectContextService:
    def __init__(self, conn: AsyncConnection) -> None:
        self._repo = ProjectContextValueRepository(conn)

    async def current_read(self, project_uuid: UUID) -> ProjectContextRead:
        return _to_read(project_uuid, await self._repo.current(project_uuid))

    async def history(self, project_uuid: UUID) -> list[ProjectContextHistory]:
        out: list[ProjectContextHistory] = []
        for name in (*GLOBALE_VARIABLEN, VAR_ENTFERNUNG_DEPONIE_KM):
            versionen = await self._repo.history(project_uuid, name)
            if versionen:
                out.append(ProjectContextHistory(variable_name=name, versionen=versionen))
        return out

    async def resolve(
        self,
        project_uuid: UUID,
        *,
        retrieval: RetrievalService,
        llm: LLMClient,
        prompt: PromptVersion | None = None,
    ) -> ProjectContextRead:
        """Resolve every global not yet present (RAG + synthesis + geocode), then derive the
        deponie distance. `prompt` is the PROJECT_CONTEXT_RESOLVE PromptVersion (unused in mock)."""
        current = await self._repo.current(project_uuid)
        location_resolved = False
        for name, gv in GLOBALE_VARIABLEN.items():
            if name in current:
                continue
            new = await self._resolve_one(project_uuid, gv, retrieval=retrieval, llm=llm, prompt=prompt)
            if new is not None:
                await self._repo.supersede(new)
                location_resolved = location_resolved or gv.ist_standort
        # Route the deponie distance only when a location was newly resolved this run (or none exists
        # yet); otherwise a no-op resolve would append a spurious ROUTING version every calculation.
        if location_resolved or VAR_ENTFERNUNG_DEPONIE_KM not in current:
            await self._recompute_deponie_distance(project_uuid)
        return await self.current_read(project_uuid)

    async def save(
        self, project_uuid: UUID, update: ProjectContextUpdate, *, benutzer: str
    ) -> ProjectContextRead:
        """Apply a user override as new HITL versions; geocode changed locations and recompute
        the deponie distance when either location moved."""
        location_changed = False
        for name in (VAR_BAUSTELLE_LOCATION, VAR_DEPONIE_LOCATION):
            wert = getattr(update, name)
            if wert is None:
                continue
            breitengrad, laengengrad, status = await self._geocode(wert)
            await self._repo.supersede(
                NewProjectContextValue(
                    project_uuid=project_uuid,
                    variable_name=name,
                    wert=wert,
                    breitengrad=breitengrad,
                    laengengrad=laengengrad,
                    quelle=ContextQuelle.HITL,
                    benutzer=benutzer,
                    status=status,
                )
            )
            location_changed = True
        for name in (VAR_STRIP_LENGTH_M, VAR_STRIP_WIDTH_M, VAR_FRAESGUT_KLASSE):
            wert = getattr(update, name)
            if wert is None:
                continue
            await self._repo.supersede(
                NewProjectContextValue(
                    project_uuid=project_uuid,
                    variable_name=name,
                    wert=wert,
                    quelle=ContextQuelle.HITL,
                    benutzer=benutzer,
                )
            )
        if location_changed:
            await self._recompute_deponie_distance(project_uuid)
        return await self.current_read(project_uuid)

    async def _resolve_one(
        self,
        project_uuid: UUID,
        gv: GlobaleVariable,
        *,
        retrieval: RetrievalService,
        llm: LLMClient,
        prompt: PromptVersion | None,
    ) -> NewProjectContextValue | None:
        if settings.calculator_mock:
            wert: str | None = _MOCK_WERTE[gv.name]
            konfidenz = Decimal("1.0")
            beleg: str | None = "(mock)"
            quelle_referenz: dict | None = None
        else:
            assert prompt is not None  # live resolution always carries the resolve prompt
            ctx = await retrieval.retrieve_context(
                gv.rag_prompt, project_uuid, RESOLVE_RETRIEVAL_CONFIG
            )
            snippets = [c.chunk_text for c in ctx.context]
            ext, _summary = await resolve_globale(
                llm, gv, snippets, prompt=prompt, project_uuid=project_uuid
            )
            if not ext.gefunden or not ext.wert:
                return None
            wert = ext.wert
            konfidenz = Decimal(str(ext.konfidenz))
            beleg = ext.beleg
            quelle_referenz = _quelle_referenz(ctx)

        breitengrad = laengengrad = None
        status: str | None = None
        if gv.ist_standort:
            breitengrad, laengengrad, status = await self._geocode(wert)
        return NewProjectContextValue(
            project_uuid=project_uuid,
            variable_name=gv.name,
            wert=wert,
            breitengrad=breitengrad,
            laengengrad=laengengrad,
            quelle=ContextQuelle.RAG,
            beleg=beleg,
            quelle_referenz=quelle_referenz,
            konfidenz=konfidenz,
            status=status,
        )

    async def _geocode(self, address: str) -> tuple[str | None, str | None, str]:
        """Geocode an address string to (breitengrad, laengengrad, status). Never raises."""
        try:
            geo = await geocode(address)
        except MapsError:
            return None, None, ContextStatus.FEHLGESCHLAGEN
        status = ContextStatus.AUFGELOEST
        if not settings.calculator_mock and geo.konfidenz < GEOCODE_UNSICHER_SCHWELLE:
            status = ContextStatus.UNSICHER
        return str(geo.breitengrad), str(geo.laengengrad), status

    async def _recompute_deponie_distance(self, project_uuid: UUID) -> None:
        """Route the current Baustelle -> Deponie and persist `entfernung_deponie_km` (ROUTING).
        A no-op until both locations are present and geocoded."""
        current = await self._repo.current(project_uuid)
        baustelle = current.get(VAR_BAUSTELLE_LOCATION)
        deponie = current.get(VAR_DEPONIE_LOCATION)
        von = _koordinate(baustelle)
        nach = _koordinate(deponie)
        if von is None or nach is None:
            return
        km = await road_distance_km(von, nach)
        referenz = {
            "provider": ROUTING_PROVIDER,
            "von": f"{VAR_BAUSTELLE_LOCATION}@v{baustelle.version}",
            "nach": f"{VAR_DEPONIE_LOCATION}@v{deponie.version}",
        }
        await self._repo.supersede(
            NewProjectContextValue(
                project_uuid=project_uuid,
                variable_name=VAR_ENTFERNUNG_DEPONIE_KM,
                wert=str(km),
                quelle=ContextQuelle.ROUTING,
                quelle_referenz=referenz,
            )
        )


def _koordinate(value: ProjectContextValue | None) -> Koordinate | None:
    if value is None or value.breitengrad is None or value.laengengrad is None:
        return None
    return (Decimal(value.breitengrad), Decimal(value.laengengrad))


def _quelle_referenz(ctx: RetrievalContext) -> dict:
    """Governance provenance for a RAG value: the retrieval policy + the contributing chunks."""
    scores = {t.chunk_uuid: t.relevance_score for t in ctx.reranked}
    treffer = [
        {
            "document_uuid": str(c.source_doc_uuid),
            "seite": c.source_doc_pages[0] if c.source_doc_pages else None,
            "chunk_uuid": str(c.chunk_uuid),
            "score": scores.get(c.chunk_uuid),
        }
        for c in ctx.context
    ]
    return {
        "retrieval": {
            "modality": ctx.config.modality.value,
            "multi_query": ctx.config.multi_query,
            "use_bm25": ctx.config.use_bm25,
            "use_cross_encoder": ctx.config.use_cross_encoder,
            "top_k": ctx.config.top_k,
        },
        "treffer": treffer,
    }


def _to_read(
    project_uuid: UUID, current: dict[str, ProjectContextValue]
) -> ProjectContextRead:
    baustelle = current.get(VAR_BAUSTELLE_LOCATION)
    deponie = current.get(VAR_DEPONIE_LOCATION)
    entfernung = current.get(VAR_ENTFERNUNG_DEPONIE_KM)
    strip_length = current.get(VAR_STRIP_LENGTH_M)
    strip_width = current.get(VAR_STRIP_WIDTH_M)
    fraesgut = current.get(VAR_FRAESGUT_KLASSE)
    return ProjectContextRead(
        project_uuid=project_uuid,
        vorhanden=bool(current),
        baustelle_location=baustelle.wert if baustelle else None,
        baustelle_breitengrad=baustelle.breitengrad if baustelle else None,
        baustelle_laengengrad=baustelle.laengengrad if baustelle else None,
        baustelle_status=baustelle.status if baustelle else None,
        deponie_location=deponie.wert if deponie else None,
        deponie_breitengrad=deponie.breitengrad if deponie else None,
        deponie_laengengrad=deponie.laengengrad if deponie else None,
        deponie_status=deponie.status if deponie else None,
        entfernung_deponie_km=entfernung.wert if entfernung else None,
        strip_length_m=strip_length.wert if strip_length else None,
        strip_width_m=strip_width.wert if strip_width else None,
        fraesgut_klasse=fraesgut.wert if fraesgut else None,
    )
