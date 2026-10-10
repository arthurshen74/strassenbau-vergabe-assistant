from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from shared.models.enums import ProjectInfoQuery

# `projects` column each query's answer is written to.
PROJECT_INFO_TARGET_COLUMN: dict[ProjectInfoQuery, str] = {
    ProjectInfoQuery.PROJECT_DESCRIPTION: "project_description",
    ProjectInfoQuery.PROJECT_MASSNAHMENUMMER: "massnahmenummer",
    ProjectInfoQuery.PROJECT_NAME: "project_name",
    ProjectInfoQuery.PROJECT_VERGABENUMMER: "vergabe_id",
    ProjectInfoQuery.PROJECT_BAULEISTUNG: "bauleistung",
    ProjectInfoQuery.PROJECT_LOCATION: "location",
    ProjectInfoQuery.PROJECT_VERGABESTELLE: "vergabestelle",
}


class RagQueryVersion(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    rag_query_version_uuid: UUID
    query_key: ProjectInfoQuery
    language: str
    version: int
    name: str
    description: str
    query_text: str
    answer_instruction: str
    created_at: datetime


class NewRagQueryVersion(BaseModel):
    """Create-model for a RAG query version. `version` is assigned by the repository
    (next integer for the (query_key, language)); PK and created_at by the DB."""

    model_config = ConfigDict(extra="forbid")

    query_key: ProjectInfoQuery
    language: str
    name: str
    description: str
    query_text: str
    answer_instruction: str
