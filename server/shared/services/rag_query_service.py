"""Business logic for the project-info RAG query versions.

Versions are immutable and append-only: each publish appends the next version for its
(query_key, language) (the repository assigns the number). The service translates
between the API DTOs and the repository's domain create-model.
"""

from __future__ import annotations

from shared.models.enums import ProjectInfoQuery
from shared.models.rag_query import NewRagQueryVersion
from shared.models.rag_query_schema import RagQueryVersionCreate, RagQueryVersionRead
from shared.repositories.rag_queries import RagQueryVersionRepository


class RagQueryService:
    def __init__(self, rag_queries: RagQueryVersionRepository) -> None:
        self.rag_queries = rag_queries

    async def list_latest(self, language: str) -> list[RagQueryVersionRead]:
        latest = await self.rag_queries.latest_all(language)
        return [RagQueryVersionRead.model_validate(v) for v in latest]

    async def history(
        self, query_key: ProjectInfoQuery, language: str
    ) -> list[RagQueryVersionRead]:
        versions = await self.rag_queries.history(query_key, language)
        return [RagQueryVersionRead.model_validate(v) for v in versions]

    async def publish(
        self, query_key: ProjectInfoQuery, payload: RagQueryVersionCreate
    ) -> RagQueryVersionRead:
        created = await self.rag_queries.add(
            NewRagQueryVersion(query_key=query_key, **payload.model_dump())
        )
        return RagQueryVersionRead.model_validate(created)
