"""Repository for project context values (per-variable version history, SCD-2).

`current`/`as_of` project the version rows down to one value per variable; `history`
returns the full ordered version list for governance. `supersede` performs the SCD-2
write: close out the current row and insert the next version, never mutating a prior
version's value or source.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.db.tables.project_context_values import project_context_values
from shared.models.project_context import NewProjectContextValue, ProjectContextValue


class ProjectContextValueRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self.conn = conn

    async def current(self, project_uuid: UUID) -> dict[str, ProjectContextValue]:
        """The current (`ist_aktuell`) version of each variable, keyed by
        variable_name."""
        stmt = select(project_context_values).where(
            project_context_values.c.project_uuid == project_uuid,
            project_context_values.c.ist_aktuell,
        )
        rows = (await self.conn.execute(stmt)).mappings().all()
        return {
            r["variable_name"]: ProjectContextValue.model_validate(dict(r))
            for r in rows
        }

    async def history(
        self, project_uuid: UUID, variable_name: str
    ) -> list[ProjectContextValue]:
        """All versions of one variable, ascending by version."""
        stmt = (
            select(project_context_values)
            .where(
                project_context_values.c.project_uuid == project_uuid,
                project_context_values.c.variable_name == variable_name,
            )
            .order_by(project_context_values.c.version)
        )
        rows = (await self.conn.execute(stmt)).mappings().all()
        return [ProjectContextValue.model_validate(dict(r)) for r in rows]

    async def as_of(
        self, project_uuid: UUID, zeitpunkt: datetime
    ) -> dict[str, ProjectContextValue]:
        """Point-in-time view: the version valid at `zeitpunkt`, keyed by
        variable_name."""
        stmt = select(project_context_values).where(
            project_context_values.c.project_uuid == project_uuid,
            project_context_values.c.gueltig_ab <= zeitpunkt,
            (project_context_values.c.gueltig_bis.is_(None))
            | (project_context_values.c.gueltig_bis > zeitpunkt),
        )
        rows = (await self.conn.execute(stmt)).mappings().all()
        return {
            r["variable_name"]: ProjectContextValue.model_validate(dict(r))
            for r in rows
        }

    async def delete_all(self, project_uuid: UUID) -> int:
        """Delete every context version for a project (all variables + full history), so
        the next resolve starts from scratch. Returns the number of rows deleted. Runs
        in the caller's UoW."""
        stmt = delete(project_context_values).where(
            project_context_values.c.project_uuid == project_uuid
        )
        return (await self.conn.execute(stmt)).rowcount

    async def supersede(self, new: NewProjectContextValue) -> ProjectContextValue:
        """Close out the current version of `new.variable_name` and insert the next
        version.

        Runs inside the caller's UoW transaction. The close-out precedes the insert so
        the partial unique index (one `ist_aktuell` per variable) never sees two current
        rows; UNIQUE(project, variable, version) + that index guard concurrent writers.
        """
        next_version_stmt = select(
            func.coalesce(func.max(project_context_values.c.version), 0) + 1
        ).where(
            project_context_values.c.project_uuid == new.project_uuid,
            project_context_values.c.variable_name == new.variable_name,
        )
        next_version = (await self.conn.execute(next_version_stmt)).scalar_one()

        # Wall-clock event time (clock_timestamp, not now()/transaction_timestamp): it
        # advances within a transaction, so versions superseded in the same UoW get
        # distinct, ordered validity intervals (point-in-time works). Fetched once so
        # the close-out boundary and the new version's start are the exact same instant
        # (a gapless SCD-2 timeline).
        now = (await self.conn.execute(select(func.clock_timestamp()))).scalar_one()

        close_out = (
            update(project_context_values)
            .where(
                project_context_values.c.project_uuid == new.project_uuid,
                project_context_values.c.variable_name == new.variable_name,
                project_context_values.c.ist_aktuell,
            )
            .values(ist_aktuell=False, gueltig_bis=now)
        )
        await self.conn.execute(close_out)

        ins = (
            insert(project_context_values)
            .values(
                version=next_version,
                ist_aktuell=True,
                gueltig_ab=now,
                **new.model_dump(),
            )
            .returning(project_context_values)
        )
        row = (await self.conn.execute(ins)).mappings().one()
        return ProjectContextValue.model_validate(dict(row))
