"""Curation-facing repository methods: gold delete, correction filters, and the
variable-by-reason summary rollup."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncConnection

from shared.models.document import NewDocument
from shared.models.enums import DocumentType, VariableCorrectionReason
from shared.models.ground_truth import (
    GoldVariable,
    NewGroundTruth,
    NewVariableCorrection,
)
from shared.models.lv_item import NewLVItem
from shared.models.project import NewProject
from shared.repositories.documents import DocumentRepository
from shared.repositories.ground_truth import GroundTruthRepository
from shared.repositories.lv_items import LVItemRepository
from shared.repositories.projects import ProjectRepository
from shared.repositories.variable_corrections import VariableCorrectionRepository

USER = UUID("00000000-0000-0000-0000-000000000001")


@dataclass
class Fixture:
    project_uuid: UUID
    lv_item_uuid: UUID


async def _fixture(conn: AsyncConnection, vergabe_id: str = "VG-GT") -> Fixture:
    project = await ProjectRepository(conn).add(
        NewProject(
            vergabe_id=vergabe_id,
            project_name="P",
            project_description="d",
            vergabestelle="V",
        )
    )
    document = await DocumentRepository(conn).add(
        NewDocument(
            project_uuid=project.project_uuid,
            document_type=DocumentType.LV_DOCUMENT,
            file_name="lv.pdf",
            number_of_pages=1,
        )
    )
    item = await LVItemRepository(conn).add(
        NewLVItem(
            document_uuid=document.document_uuid,
            oz="01.02.0030",
            kurztext="Asphalt fräsen",
            langtext="Asphalt fräsen, Tiefe 4 cm",
            menge=Decimal("100"),
            einheit="m2",
        )
    )
    return Fixture(project_uuid=project.project_uuid, lv_item_uuid=item.lv_item_uuid)


def _new_gold(fx: Fixture) -> NewGroundTruth:
    return NewGroundTruth(
        project_uuid=fx.project_uuid,
        lv_item_uuid=fx.lv_item_uuid,
        oz="01.02.0030",
        leistung_key="L_FRAESEN",
        gold_variables={"tiefe_cm": GoldVariable(wert="4", art="eingabe")},
        created_by_user_id=USER,
    )


def _correction(
    fx: Fixture, variable_name: str, reason: VariableCorrectionReason | None
) -> NewVariableCorrection:
    return NewVariableCorrection(
        project_uuid=fx.project_uuid,
        variable_name=variable_name,
        final_wert="1",
        reason=reason,
        created_by_user_id=USER,
    )


async def test_delete_gold(conn: AsyncConnection) -> None:
    fx = await _fixture(conn)
    repo = GroundTruthRepository(conn)
    await repo.upsert(_new_gold(fx))

    assert await repo.delete(fx.project_uuid, fx.lv_item_uuid) is True
    assert await repo.get(fx.project_uuid, fx.lv_item_uuid) is None
    assert await repo.delete(fx.project_uuid, fx.lv_item_uuid) is False
    assert await repo.delete(uuid4(), fx.lv_item_uuid) is False


async def test_correction_filters(conn: AsyncConnection) -> None:
    fx = await _fixture(conn, vergabe_id="VG-GT-F")
    repo = VariableCorrectionRepository(conn)
    await repo.add_many(
        [
            _correction(fx, "tiefe_cm", VariableCorrectionReason.FALSCHER_WERT),
            _correction(fx, "tiefe_cm", VariableCorrectionReason.KALKULATOR_ERMESSEN),
            _correction(fx, "laenge_m", VariableCorrectionReason.FALSCHER_WERT),
        ]
    )

    assert len(await repo.list_by_project(fx.project_uuid)) == 3
    assert len(await repo.list_by_project(fx.project_uuid, variable_name="tiefe_cm")) == 2
    assert (
        len(
            await repo.list_by_project(
                fx.project_uuid, reason=VariableCorrectionReason.FALSCHER_WERT
            )
        )
        == 2
    )
    both = await repo.list_by_project(
        fx.project_uuid,
        variable_name="tiefe_cm",
        reason=VariableCorrectionReason.FALSCHER_WERT,
    )
    assert len(both) == 1


async def test_correction_summary_groups_and_orders(conn: AsyncConnection) -> None:
    fx = await _fixture(conn, vergabe_id="VG-GT-S")
    repo = VariableCorrectionRepository(conn)
    await repo.add_many(
        [
            _correction(fx, "tiefe_cm", VariableCorrectionReason.FALSCHER_WERT),
            _correction(fx, "tiefe_cm", VariableCorrectionReason.FALSCHER_WERT),
            _correction(fx, "laenge_m", None),
        ]
    )

    summary = await repo.summary_by_project(fx.project_uuid)
    assert [(s.variable_name, s.reason, s.count) for s in summary] == [
        ("tiefe_cm", VariableCorrectionReason.FALSCHER_WERT, 2),
        ("laenge_m", None, 1),
    ]
