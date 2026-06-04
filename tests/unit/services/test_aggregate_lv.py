"""The deterministic core of aggregate_lv_items: the LLM picks members, Python sums the menge.

These tests fake the LV repository and the membership LLM, so they exercise only the arithmetic and
bucketing -- the part that must be exact: per-einheit Decimal sums, the unit filter, the
Bedarfs-/Eventualposition split, coverage counting, and dropping a hallucinated uuid."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from shared.models.llm_output_schemas import LVMembership, LVMembershipItem
from shared.models.lv_item import LVItem
from shared.services import aggregate_lv
from shared.services.aggregate_lv import AggregateLVService, _normalize_unit


def _item(oz: str, menge: str, einheit: str, positionstyp: str | None = None) -> LVItem:
    return LVItem(
        lv_item_uuid=uuid4(),
        document_uuid=uuid4(),
        oz=oz,
        kurztext=f"Pos {oz}",
        langtext="",
        menge=Decimal(menge),
        einheit=einheit,
        positionstyp=positionstyp,
        last_ingestion=datetime.now(UTC),
    )


class _FakeConn:
    async def __aenter__(self) -> "_FakeConn":
        return self

    async def __aexit__(self, *_exc: object) -> bool:
        return False


class _FakeEngine:
    def connect(self) -> _FakeConn:
        return _FakeConn()


def _patch(monkeypatch, items: list[LVItem], matched_uuids: list[str]) -> None:
    class _Repo:
        def __init__(self, _conn: object) -> None:
            pass

        async def list_by_project(self, _project_uuid: object) -> list[LVItem]:
            return items

    class _Runner:
        def __init__(self, _prompts: object, _llm: object) -> None:
            pass

        async def run_lv_membership(
            self,
            _predicate: str,
            _listing: str,
            *,
            project_uuid: object,
            conversation_uuid: object = None,
        ) -> LVMembership:
            return LVMembership(
                matched=[LVMembershipItem(lv_item_uuid=u, rationale="r") for u in matched_uuids]
            )

    monkeypatch.setattr(aggregate_lv, "LVItemRepository", _Repo)
    monkeypatch.setattr(aggregate_lv, "PromptVersionRepository", lambda _conn: None)
    monkeypatch.setattr(aggregate_lv, "PromptRunner", _Runner)


def _service() -> AggregateLVService:
    return AggregateLVService(engine=_FakeEngine(), llm=object())  # type: ignore[arg-type]


async def test_sums_by_einheit_excluding_contingency_and_unmatched(monkeypatch) -> None:
    items = [
        _item("01.01", "10.5", "m³"),
        _item("01.02", "4.5", "m³"),
        _item("01.03", "3", "m²"),
        _item("01.04", "99", "m³", "Bedarfsposition"),
        _item("01.05", "7", "m³"),  # not matched
    ]
    matched = [str(i.lv_item_uuid) for i in items[:4]]
    _patch(monkeypatch, items, matched)

    result = await _service().aggregate("Erdaushub", uuid4())

    by_unit = {s.einheit: s for s in result.per_unit}
    assert by_unit["m³"].total == Decimal("15.0")  # 10.5 + 4.5; 99 is contingency, 7 unmatched
    assert by_unit["m³"].count == 2
    assert by_unit["m²"].total == Decimal("3")
    assert len(result.breakdown) == 3  # regular matched only
    assert [i.oz for i in result.bedarfs_eventual] == ["01.04"]
    assert result.coverage.matched == 4
    assert result.coverage.total == 5


async def test_unit_filter_restricts_subtotals(monkeypatch) -> None:
    items = [_item("1", "10", "m³"), _item("2", "5", "m²")]
    _patch(monkeypatch, items, [str(i.lv_item_uuid) for i in items])

    result = await _service().aggregate("x", uuid4(), unit="m3")  # m3 normalises to m³

    assert [s.einheit for s in result.per_unit] == ["m³"]
    assert result.per_unit[0].total == Decimal("10")


async def test_hallucinated_uuid_is_dropped(monkeypatch) -> None:
    items = [_item("1", "10", "m³")]
    matched = [str(items[0].lv_item_uuid), str(uuid4())]  # second uuid is invented
    _patch(monkeypatch, items, matched)

    result = await _service().aggregate("x", uuid4())

    assert result.coverage.matched == 1
    assert result.per_unit[0].total == Decimal("10")


def test_normalize_unit_aliases() -> None:
    assert _normalize_unit("m3") == "m³"
    assert _normalize_unit(" CBM ") == "m³"
    assert _normalize_unit("qm") == "m²"
    assert _normalize_unit("Stk") == "stk"
