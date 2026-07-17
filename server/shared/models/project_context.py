"""Domain models for project-scoped context globals (per-variable version history).

`ProjectContextValue` is one immutable version row; `NewProjectContextValue` is the
insert shape the repository turns into the next version (computing `version` and closing
out the prior current row). Provenance per version lives in `quelle`, `beleg`,
`quelle_referenz` and `konfidenz` (see PROJECT_CONTEXT_PLAN.md §5).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from shared.models.enums import ContextQuelle


class ProjectContextValue(BaseModel):
    """One version of a project context variable."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    project_context_value_uuid: UUID
    project_uuid: UUID
    variable_name: str
    version: int
    wert: str
    breitengrad: str | None = None
    laengengrad: str | None = None
    quelle: ContextQuelle
    beleg: str | None = None
    quelle_referenz: dict | None = None
    konfidenz: Decimal | None = None
    benutzer: str | None = None
    status: str | None = None
    ist_aktuell: bool
    gueltig_ab: datetime
    gueltig_bis: datetime | None = None
    erstellt_am: datetime


class NewProjectContextValue(BaseModel):
    """Insert shape; the repository computes `version` and closes out the prior
    version."""

    model_config = ConfigDict(extra="forbid")

    project_uuid: UUID
    variable_name: str
    wert: str
    breitengrad: str | None = None
    laengengrad: str | None = None
    quelle: ContextQuelle
    beleg: str | None = None
    quelle_referenz: dict | None = None
    konfidenz: Decimal | None = None
    benutzer: str | None = None
    status: str | None = None
