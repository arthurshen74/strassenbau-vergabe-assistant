from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.config import settings
from shared.models.enums import ContextQuelle
from shared.models.project import NewProject
from shared.models.project_context_schema import ProjectContextUpdate
from shared.repositories.projects import ProjectRepository
from shared.services.project_context import ProjectContextService

DEFAULT_USER = "DEFAULT_USER"


async def _project(conn: AsyncConnection) -> UUID:
    project = await ProjectRepository(conn).add(
        NewProject(
            vergabe_id="VG-PCS",
            project_name="P",
            project_description="d",
            vergabestelle="V",
        )
    )
    return project.project_uuid


@pytest.fixture(autouse=True)
def _mock_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "calculator_mock", True)


async def test_resolve_mock_fills_globals_and_distance(conn: AsyncConnection) -> None:
    project_uuid = await _project(conn)
    service = ProjectContextService(conn)

    read = await service.resolve(project_uuid, retrieval=None, llm=None, prompt=None)  # type: ignore[arg-type]

    assert read.vorhanden is True
    assert read.baustelle_location == "Baustelle L 101, Nordhausen"
    assert read.baustelle_breitengrad == "51.42"
    assert read.baustelle_laengengrad == "10.81"
    assert read.baustelle_status == "aufgeloest"
    assert read.deponie_location == "Deponie Sangerhausen"
    assert read.strip_length_m == "5100"
    assert read.strip_width_m == "1.0"
    assert read.fraesgut_klasse == "1"
    # Both locations geocoded -> the routed deponie distance is derived.
    assert read.entfernung_deponie_km is not None


async def test_resolve_is_idempotent_for_present_globals(conn: AsyncConnection) -> None:
    project_uuid = await _project(conn)
    service = ProjectContextService(conn)
    await service.resolve(project_uuid, retrieval=None, llm=None, prompt=None)  # type: ignore[arg-type]

    # A second resolve must not append versions for already-present globals.
    await service.resolve(project_uuid, retrieval=None, llm=None, prompt=None)  # type: ignore[arg-type]

    history = {h.variable_name: h.versionen for h in await service.history(project_uuid)}
    assert [v.version for v in history["strip_length_m"]] == [1]
    assert [v.version for v in history["baustelle_location"]] == [1]


async def test_save_appends_hitl_version_and_recomputes_distance(
    conn: AsyncConnection,
) -> None:
    project_uuid = await _project(conn)
    service = ProjectContextService(conn)
    await service.resolve(project_uuid, retrieval=None, llm=None, prompt=None)  # type: ignore[arg-type]

    read = await service.save(
        project_uuid,
        ProjectContextUpdate(strip_length_m="6000", baustelle_location="Andere Straße 5"),
        benutzer=DEFAULT_USER,
    )

    assert read.strip_length_m == "6000"
    assert read.baustelle_location == "Andere Straße 5"

    history = {h.variable_name: h.versionen for h in await service.history(project_uuid)}
    strip = history["strip_length_m"]
    assert [v.version for v in strip] == [1, 2]
    assert strip[1].quelle == ContextQuelle.HITL
    assert strip[1].benutzer == DEFAULT_USER
    # The unchanged strip_width keeps its single RAG version.
    assert [v.version for v in history["strip_width_m"]] == [1]
    # Changing a location reroutes the deponie distance (a new ROUTING version).
    assert [v.version for v in history["entfernung_deponie_km"]] == [1, 2]
    assert history["entfernung_deponie_km"][1].quelle == ContextQuelle.ROUTING


async def test_save_numeric_only_does_not_reroute(conn: AsyncConnection) -> None:
    project_uuid = await _project(conn)
    service = ProjectContextService(conn)
    await service.resolve(project_uuid, retrieval=None, llm=None, prompt=None)  # type: ignore[arg-type]

    await service.save(
        project_uuid, ProjectContextUpdate(fraesgut_klasse="2"), benutzer=DEFAULT_USER
    )

    history = {h.variable_name: h.versionen for h in await service.history(project_uuid)}
    # No location changed -> the deponie distance is not recomputed.
    assert [v.version for v in history["entfernung_deponie_km"]] == [1]
    assert [v.version for v in history["fraesgut_klasse"]] == [1, 2]
