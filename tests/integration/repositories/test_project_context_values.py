from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

from shared.models.enums import ContextQuelle
from shared.models.project import NewProject
from shared.models.project_context import NewProjectContextValue
from shared.repositories.project_context_values import ProjectContextValueRepository
from shared.repositories.projects import ProjectRepository


async def _project(conn: AsyncConnection) -> UUID:
    project = await ProjectRepository(conn).add(
        NewProject(
            vergabe_id="VG-PCV",
            project_name="P",
            project_description="d",
            vergabestelle="V",
        )
    )
    return project.project_uuid


def _new(project_uuid: UUID, name: str, wert: str, **kw: object) -> NewProjectContextValue:
    kw.setdefault("quelle", ContextQuelle.RAG)
    return NewProjectContextValue(
        project_uuid=project_uuid,
        variable_name=name,
        wert=wert,
        **kw,
    )


async def test_supersede_first_version_is_one_and_current(conn: AsyncConnection) -> None:
    repo = ProjectContextValueRepository(conn)
    project_uuid = await _project(conn)

    v1 = await repo.supersede(_new(project_uuid, "strip_length_m", "5100"))

    assert v1.version == 1
    assert v1.ist_aktuell is True
    assert v1.gueltig_bis is None
    current = await repo.current(project_uuid)
    assert set(current) == {"strip_length_m"}
    assert current["strip_length_m"].wert == "5100"


async def test_supersede_closes_out_and_inserts_next_version(
    conn: AsyncConnection,
) -> None:
    repo = ProjectContextValueRepository(conn)
    project_uuid = await _project(conn)

    v1 = await repo.supersede(_new(project_uuid, "fraesgut_klasse", "1"))
    v2 = await repo.supersede(
        _new(project_uuid, "fraesgut_klasse", "2", quelle=ContextQuelle.HITL, benutzer="DEFAULT_USER")
    )

    assert v2.version == 2
    assert v2.ist_aktuell is True

    history = await repo.history(project_uuid, "fraesgut_klasse")
    assert [h.version for h in history] == [1, 2]
    closed = history[0]
    # The prior version is closed out, never mutated in value/source.
    assert closed.ist_aktuell is False
    assert closed.gueltig_bis is not None
    assert closed.wert == "1"
    assert closed.quelle == ContextQuelle.RAG
    assert closed.project_context_value_uuid == v1.project_context_value_uuid

    current = await repo.current(project_uuid)
    assert current["fraesgut_klasse"].wert == "2"
    assert current["fraesgut_klasse"].quelle == ContextQuelle.HITL
    assert current["fraesgut_klasse"].benutzer == "DEFAULT_USER"


async def test_current_one_row_per_variable(conn: AsyncConnection) -> None:
    repo = ProjectContextValueRepository(conn)
    project_uuid = await _project(conn)

    await repo.supersede(_new(project_uuid, "strip_length_m", "5100"))
    await repo.supersede(_new(project_uuid, "strip_width_m", "1.0"))
    await repo.supersede(_new(project_uuid, "strip_width_m", "1.5"))

    current = await repo.current(project_uuid)
    assert set(current) == {"strip_length_m", "strip_width_m"}
    assert current["strip_width_m"].wert == "1.5"
    assert current["strip_width_m"].version == 2


async def test_as_of_point_in_time(conn: AsyncConnection) -> None:
    repo = ProjectContextValueRepository(conn)
    project_uuid = await _project(conn)

    v1 = await repo.supersede(_new(project_uuid, "strip_width_m", "1.0"))
    await repo.supersede(_new(project_uuid, "strip_width_m", "2.0"))

    # v1.gueltig_ab is a server timestamp squarely inside v1's validity interval [v1.gueltig_ab,
    # v2.gueltig_ab); using a DB clock avoids client/server skew. Only v1 was valid then.
    as_of = await repo.as_of(project_uuid, v1.gueltig_ab)
    assert as_of["strip_width_m"].wert == "1.0"
    assert as_of["strip_width_m"].project_context_value_uuid == v1.project_context_value_uuid

    # Before any version existed nothing is returned.
    assert await repo.as_of(project_uuid, v1.gueltig_ab.replace(year=2000)) == {}


async def test_supersede_preserves_provenance_columns(conn: AsyncConnection) -> None:
    repo = ProjectContextValueRepository(conn)
    project_uuid = await _project(conn)

    value = await repo.supersede(
        _new(
            project_uuid,
            "baustelle_location",
            "Nordhausen, L 101",
            breitengrad="51.42",
            laengengrad="10.81",
            beleg="Die Baustelle liegt an der L 101 bei Nordhausen.",
            quelle_referenz={"retrieval": {"top_k": 8}, "treffer": [{"document_uuid": "x"}]},
            konfidenz=Decimal("0.9"),
            status="aufgeloest",
        )
    )

    fetched = (await repo.current(project_uuid))["baustelle_location"]
    assert fetched.breitengrad == "51.42"
    assert fetched.laengengrad == "10.81"
    assert fetched.beleg == value.beleg
    assert fetched.quelle_referenz == {"retrieval": {"top_k": 8}, "treffer": [{"document_uuid": "x"}]}
    assert fetched.konfidenz == Decimal("0.9")
    assert fetched.status == "aufgeloest"
