from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncConnection

from shared.models.enums import (
    NerFailureCategory,
    NerFlagKind,
    NerFlagStatus,
)
from shared.models.ner_flag import NewNerFlag, SnapshotEntity, SuggestedRule
from shared.repositories.ner_flags import NerFlagRepository


def _new(
    kind: NerFlagKind = NerFlagKind.WRONG_LABEL,
    label: str = "LOC",
    **kw: object,
) -> NewNerFlag:
    return NewNerFlag(
        kind=kind,
        span_text="Asphaltbeton AC",
        span_start=0,
        span_end=15,
        sentence_text="Asphaltbeton AC einbauen.",
        label=label,
        user_comment="LOC is wrong, this is a Baustoff.",
        source_text="Asphaltbeton AC einbauen.",
        entity_snapshot=[
            SnapshotEntity(text="Asphaltbeton AC", label="LOC", pattern_id=None)
        ],
        **kw,
    )


async def test_add_get_roundtrip_with_snapshot(conn: AsyncConnection) -> None:
    repo = NerFlagRepository(conn)

    created = await repo.add(_new(expected_label="BAUSTOFF"))

    assert created.status == NerFlagStatus.OPEN
    assert created.category is None
    assert created.effective_category is None
    assert created.expected_label == "BAUSTOFF"
    assert created.entity_snapshot[0].text == "Asphaltbeton AC"

    fetched = await repo.get(created.ner_flag_uuid)
    assert fetched is not None
    assert fetched.ner_flag_uuid == created.ner_flag_uuid
    assert fetched.entity_snapshot[0].pattern_id is None


async def test_update_analysis_and_suggested_rule(conn: AsyncConnection) -> None:
    repo = NerFlagRepository(conn)
    created = await repo.add(_new())

    updated = await repo.update(
        created.ner_flag_uuid,
        category=NerFailureCategory.REGISTER_MISMATCH.value,
        llm_analysis="News-trained model mislabels technical vocabulary.",
        suggested_rule=SuggestedRule(
            label="BAUSTOFF", pattern="Asphaltbeton", pattern_id="baustoff_asphaltbeton"
        ).model_dump(mode="json"),
        llm_model="openai/gpt-5.4",
        prompt_version=1,
        spacy_model_version="de_core_news_lg-3.8.0",
    )

    assert updated is not None
    assert updated.category == NerFailureCategory.REGISTER_MISMATCH
    assert updated.effective_category == NerFailureCategory.REGISTER_MISMATCH
    assert updated.suggested_rule is not None
    assert updated.suggested_rule.pattern_id == "baustoff_asphaltbeton"
    assert updated.prompt_version == 1


async def test_override_wins_for_effective_category(conn: AsyncConnection) -> None:
    repo = NerFlagRepository(conn)
    created = await repo.add(_new())
    await repo.update(
        created.ner_flag_uuid, category=NerFailureCategory.MODEL_LIMITATION.value
    )

    overridden = await repo.update(
        created.ner_flag_uuid,
        category_override=NerFailureCategory.REGISTER_MISMATCH.value,
    )

    assert overridden is not None
    assert overridden.category == NerFailureCategory.MODEL_LIMITATION
    assert overridden.effective_category == NerFailureCategory.REGISTER_MISMATCH


async def test_list_filters(conn: AsyncConnection) -> None:
    repo = NerFlagRepository(conn)
    wrong = await repo.add(_new(kind=NerFlagKind.WRONG_LABEL))
    await repo.update(wrong.ner_flag_uuid, category=NerFailureCategory.MISSING_RULE.value)
    missed = await repo.add(_new(kind=NerFlagKind.MISSED_ENTITY))
    await repo.update(
        missed.ner_flag_uuid,
        category=NerFailureCategory.TOKENIZATION.value,
        status=NerFlagStatus.RESOLVED.value,
        resolved_note="added rule",
    )

    by_kind = await repo.list(kind=NerFlagKind.MISSED_ENTITY)
    assert {f.ner_flag_uuid for f in by_kind} == {missed.ner_flag_uuid}

    by_category = await repo.list(category=NerFailureCategory.MISSING_RULE)
    assert {f.ner_flag_uuid for f in by_category} == {wrong.ner_flag_uuid}

    by_status = await repo.list(status=NerFlagStatus.RESOLVED)
    assert {f.ner_flag_uuid for f in by_status} == {missed.ner_flag_uuid}


async def test_category_counts_uses_effective_and_splits_status(
    conn: AsyncConnection,
) -> None:
    repo = NerFlagRepository(conn)
    # Two register-mismatch (one via override), one resolved missing-rule, one un-analyzed.
    a = await repo.add(_new())
    await repo.update(a.ner_flag_uuid, category=NerFailureCategory.REGISTER_MISMATCH.value)
    b = await repo.add(_new())
    await repo.update(
        b.ner_flag_uuid,
        category=NerFailureCategory.MODEL_LIMITATION.value,
        category_override=NerFailureCategory.REGISTER_MISMATCH.value,
    )
    c = await repo.add(_new())
    await repo.update(
        c.ner_flag_uuid,
        category=NerFailureCategory.MISSING_RULE.value,
        status=NerFlagStatus.RESOLVED.value,
        resolved_note="fixed",
    )
    await repo.add(_new())  # un-analyzed -> category None

    summary = await repo.category_counts()
    by_cat = {c.category: c for c in summary.by_category}

    assert summary.total == 4
    assert by_cat[NerFailureCategory.REGISTER_MISMATCH].total == 2
    assert by_cat[NerFailureCategory.REGISTER_MISMATCH].open_count == 2
    assert by_cat[NerFailureCategory.MISSING_RULE].resolved_count == 1
    assert by_cat[NerFailureCategory.MISSING_RULE].open_count == 0
    assert by_cat[None].total == 1


async def test_delete(conn: AsyncConnection) -> None:
    repo = NerFlagRepository(conn)
    created = await repo.add(_new())

    await repo.delete(created.ner_flag_uuid)

    assert await repo.get(created.ner_flag_uuid) is None
