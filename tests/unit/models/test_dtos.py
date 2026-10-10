from __future__ import annotations

import pytest
from pydantic import BaseModel, ValidationError

from shared.models.document import Document
from shared.models.document_schema import DocumentCreate, DocumentRead
from shared.models.ingest_job import IngestJob
from shared.models.ingest_job_event import IngestJobEvent
from shared.models.ingest_schema import (
    IngestCompleted,
    IngestError,
    IngestJobEventRead,
    IngestJobRead,
    IngestProgress,
    IngestStarted,
    IngestStatusRead,
)
from shared.models.project import Project
from shared.models.project_schema import ProjectCreate, ProjectRead, ProjectUpdate
from shared.models.prompt_version import NewPromptVersion, PromptVersion
from shared.models.prompt_version_schema import PromptVersionCreate, PromptVersionRead
from shared.models.rag_query import RagQueryVersion
from shared.models.rag_query_schema import RagQueryVersionCreate, RagQueryVersionRead

# Read DTO -> domain model: every exposed field must exist on the domain model with
# the same annotation.
READ_PARITY: list[tuple[type[BaseModel], type[BaseModel]]] = [
    (ProjectRead, Project),
    (DocumentRead, Document),
    (IngestJobRead, IngestJob),
    (IngestJobEventRead, IngestJobEvent),
    (PromptVersionRead, PromptVersion),
    (RagQueryVersionRead, RagQueryVersion),
]

ALL_DTOS: list[type[BaseModel]] = [
    ProjectCreate,
    ProjectRead,
    ProjectUpdate,
    DocumentCreate,
    DocumentRead,
    IngestJobRead,
    IngestJobEventRead,
    IngestStatusRead,
    IngestStarted,
    IngestProgress,
    IngestCompleted,
    IngestError,
    PromptVersionRead,
    PromptVersionCreate,
    RagQueryVersionRead,
    RagQueryVersionCreate,
]


@pytest.mark.parametrize("dto, domain", READ_PARITY)
def test_read_dto_matches_domain_fields(
    dto: type[BaseModel], domain: type[BaseModel]
) -> None:
    dto_fields = dto.model_fields
    domain_fields = domain.model_fields
    assert set(dto_fields) <= set(domain_fields)
    for name, field in dto_fields.items():
        assert field.annotation == domain_fields[name].annotation


def test_prompt_version_create_matches_new_prompt_version() -> None:
    create_fields = PromptVersionCreate.model_fields
    new_fields = NewPromptVersion.model_fields
    assert set(create_fields) == set(new_fields)
    for name, field in create_fields.items():
        assert field.annotation == new_fields[name].annotation


@pytest.mark.parametrize("dto", ALL_DTOS)
def test_dto_forbids_extra(dto: type[BaseModel]) -> None:
    assert dto.model_config.get("extra") == "forbid"


def test_extra_key_rejected() -> None:
    with pytest.raises(ValidationError):
        ProjectCreate(
            vergabe_id="VG-1",
            project_name="A1",
            project_description="desc",
            vergabestelle="Behörde",
            surprise="nope",
        )
