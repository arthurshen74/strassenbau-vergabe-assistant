"""Queue mechanics of the eval_runs repository: claim ordering, lease expiry reclaim, fenced
finalize, poison-run parking, plus the events and results companions."""

from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import text, update
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.db.tables.eval_runs import eval_runs
from shared.models.enums import EvalRunKind, EvalRunStatus
from shared.models.eval_run import NewEvalRun
from shared.repositories.eval_results import EvalResultRepository
from shared.repositories.eval_run_events import EvalRunEventRepository
from shared.repositories.eval_runs import EvalRunRepository

USER = UUID("00000000-0000-0000-0000-000000000001")


def _new(kind: EvalRunKind = EvalRunKind.CHAT_VALUES) -> NewEvalRun:
    return NewEvalRun(kind=kind, params={"abs_tol": "0"}, created_by_user_id=USER)


async def _backdate_lease(conn: AsyncConnection, eval_run_uuid: UUID) -> None:
    """Age the lease past any window. now() is frozen per transaction (and the test runs in
    one), so expiry must be simulated by moving locked_at into the past, not by waiting."""
    await conn.execute(
        update(eval_runs)
        .where(eval_runs.c.eval_run_uuid == eval_run_uuid)
        .values(locked_at=text("now() - interval '1 hour'"))
    )


async def test_claim_oldest_first_and_running_not_reclaimable(conn: AsyncConnection) -> None:
    repo = EvalRunRepository(conn)
    first = await repo.add(_new())
    await repo.add(_new())

    claimed = await repo.claim_next(worker_id="w1", lease_seconds=60, max_attempts=3)
    assert claimed is not None
    assert claimed.eval_run_uuid == first.eval_run_uuid
    assert claimed.status == EvalRunStatus.RUNNING
    assert claimed.attempts == 1
    assert claimed.locked_by == "w1"

    # The second claim gets the second run; a live RUNNING lease is not reclaimable.
    second = await repo.claim_next(worker_id="w2", lease_seconds=60, max_attempts=3)
    assert second is not None and second.eval_run_uuid != first.eval_run_uuid
    assert await repo.claim_next(worker_id="w3", lease_seconds=60, max_attempts=3) is None


async def test_expired_lease_is_reclaimed_and_exhausted_is_parked(
    conn: AsyncConnection,
) -> None:
    repo = EvalRunRepository(conn)
    run = await repo.add(_new())
    claimed = await repo.claim_next(worker_id="w1", lease_seconds=60, max_attempts=2)
    assert claimed is not None

    # Expired lease: the RUNNING run is reclaimable (attempts 1 < 2).
    await _backdate_lease(conn, run.eval_run_uuid)
    reclaimed = await repo.claim_next(worker_id="w2", lease_seconds=60, max_attempts=2)
    assert reclaimed is not None
    assert reclaimed.eval_run_uuid == run.eval_run_uuid
    assert reclaimed.attempts == 2
    assert reclaimed.locked_by == "w2"

    # Retry budget spent: no longer claimable; park_exhausted marks it FAILED.
    await _backdate_lease(conn, run.eval_run_uuid)
    assert await repo.claim_next(worker_id="w3", lease_seconds=60, max_attempts=2) is None
    parked = await repo.park_exhausted(lease_seconds=60, max_attempts=2)
    assert parked == 1
    parked_run = await repo.get(run.eval_run_uuid)
    assert parked_run is not None and parked_run.status == EvalRunStatus.FAILED


async def test_finalize_is_fenced_on_the_lease(conn: AsyncConnection) -> None:
    repo = EvalRunRepository(conn)
    await repo.add(_new())
    claimed = await repo.claim_next(worker_id="w1", lease_seconds=60, max_attempts=3)
    assert claimed is not None

    # A worker that lost the lease cannot finalize.
    lost = await repo.finalize(
        claimed.eval_run_uuid,
        status=EvalRunStatus.DONE,
        expected_worker="somebody-else",
    )
    assert lost is None

    done = await repo.finalize(
        claimed.eval_run_uuid,
        status=EvalRunStatus.DONE,
        expected_worker="w1",
        summary={"metrics": {"value_accuracy": 1.0}},
        prompt_versions={"ekt_chat_values": 3},
    )
    assert done is not None
    assert done.status == EvalRunStatus.DONE
    assert done.locked_at is None
    assert done.summary == {"metrics": {"value_accuracy": 1.0}}
    assert done.prompt_versions == {"ekt_chat_values": 3}


async def test_events_and_results_roundtrip(conn: AsyncConnection) -> None:
    runs = EvalRunRepository(conn)
    events = EvalRunEventRepository(conn)
    results = EvalResultRepository(conn)
    run = await runs.add(_new())

    await events.add(run.eval_run_uuid, "claimed")
    await events.add(run.eval_run_uuid, "fixture-1: 2/2 gold values correct")
    listed = await events.list_by_run(run.eval_run_uuid)
    assert [e.message for e in listed] == [
        "claimed",
        "fixture-1: 2/2 gold values correct",
    ]

    await results.add_many(
        run.eval_run_uuid,
        [("fixture-1", {"id": "fixture-1", "assignments": []})],
    )
    rows = await results.list_by_run(run.eval_run_uuid)
    assert len(rows) == 1
    assert rows[0].item_id == "fixture-1"
    assert rows[0].payload["id"] == "fixture-1"

    assert await events.list_by_run(uuid4()) == []
    assert await results.list_by_run(uuid4()) == []


async def test_list_filters_by_project(conn: AsyncConnection) -> None:
    repo = EvalRunRepository(conn)
    await repo.add(_new())
    listed = await repo.list()
    assert len(listed) >= 1
    # chat_values runs carry no project; a project filter excludes them.
    assert await repo.list(project_uuid=uuid4()) == []
