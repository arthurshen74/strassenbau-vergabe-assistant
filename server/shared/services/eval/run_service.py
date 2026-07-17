"""Read/enqueue side of the eval-run queue (the worker's claim/execute side lives in
worker.eval_loop). Enqueue validates the kind is implemented and that project-bound
kinds carry an existing project; reads serve the runs UI (list, detail, events,
results)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

from shared.models.enums import EvalRunKind
from shared.models.eval_run import (
    EvalRun,
    EvalRunCreate,
    EvalRunEvent,
    EvalResult,
    NewEvalRun,
)
from shared.repositories.eval_results import EvalResultRepository
from shared.repositories.eval_run_events import EvalRunEventRepository
from shared.repositories.eval_runs import EvalRunRepository
from shared.repositories.projects import ProjectRepository

# Kinds the worker can execute today; rag_* land with the Phase-6 graders.
SUPPORTED_KINDS = frozenset({EvalRunKind.CALCULATOR_GOLD, EvalRunKind.CHAT_VALUES})

# Kinds that grade one project's data and therefore need a project scope.
PROJECT_BOUND_KINDS = frozenset(
    {EvalRunKind.CALCULATOR_GOLD, EvalRunKind.RAG_RETRIEVAL, EvalRunKind.RAG_ANSWERS}
)


class EvalRunService:
    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn
        self._runs = EvalRunRepository(conn)
        self._events = EvalRunEventRepository(conn)
        self._results = EvalResultRepository(conn)

    async def enqueue(self, payload: EvalRunCreate, *, user_id: UUID) -> EvalRun:
        """Raises ValueError on an unsupported kind or a missing/unknown project
        scope."""
        if payload.kind not in SUPPORTED_KINDS:
            raise ValueError(f"eval kind {payload.kind.value!r} is not implemented yet")
        if payload.kind in PROJECT_BOUND_KINDS:
            if payload.project_uuid is None:
                raise ValueError(
                    f"eval kind {payload.kind.value!r} requires a project_uuid"
                )
            if await ProjectRepository(self._conn).get(payload.project_uuid) is None:
                raise ValueError("project not found")
        return await self._runs.add(
            NewEvalRun(**payload.model_dump(), created_by_user_id=user_id)
        )

    async def list_runs(
        self, *, project_uuid: UUID | None = None, limit: int = 50
    ) -> list[EvalRun]:
        return await self._runs.list(project_uuid=project_uuid, limit=limit)

    async def get_run(self, eval_run_uuid: UUID) -> EvalRun | None:
        return await self._runs.get(eval_run_uuid)

    async def events(self, eval_run_uuid: UUID) -> list[EvalRunEvent]:
        return await self._events.list_by_run(eval_run_uuid)

    async def results(self, eval_run_uuid: UUID) -> list[EvalResult]:
        return await self._results.list_by_run(eval_run_uuid)
