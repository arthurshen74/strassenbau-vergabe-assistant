from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict

from api.schemas.document import ProjectDocumentDTO


class UploadResponseDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    documents: list[ProjectDocumentDTO]
    ingest_job_ids: list[UUID]
