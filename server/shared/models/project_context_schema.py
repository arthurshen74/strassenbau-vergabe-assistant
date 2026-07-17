"""API/calc-facing projections of the project context (the flat current view +
governance).

`ProjectContextRead` flattens the current version of every variable into one object the
UI and the calc consume (addresses as strings; coords + deponie distance derived).
`ProjectContextUpdate` is the editable subset an override posts (each changed field
appends a new version). `ProjectContextHistory` is the per-variable version list for
governance.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict

from shared.models.project_context import ProjectContextValue


class ProjectContextRead(BaseModel):
    """Projection of the current version across every context variable."""

    model_config = ConfigDict(extra="forbid")

    project_uuid: UUID
    vorhanden: bool  # any version exists yet
    baustelle_location: str | None = None
    baustelle_breitengrad: str | None = None
    baustelle_laengengrad: str | None = None
    baustelle_status: str | None = None
    deponie_location: str | None = None
    deponie_breitengrad: str | None = None
    deponie_laengengrad: str | None = None
    deponie_status: str | None = None
    entfernung_deponie_km: str | None = None
    strip_length_m: str | None = None
    strip_width_m: str | None = None
    fraesgut_klasse: str | None = None


class ProjectContextUpdate(BaseModel):
    """Editable subset; each non-null field appends a new HITL version."""

    model_config = ConfigDict(extra="forbid")

    baustelle_location: str | None = None
    deponie_location: str | None = None
    strip_length_m: str | None = None
    strip_width_m: str | None = None
    fraesgut_klasse: str | None = None


class ProjectContextHistory(BaseModel):
    """Full version history for one variable (governance view)."""

    model_config = ConfigDict(extra="forbid")

    variable_name: str
    versionen: list[ProjectContextValue]
