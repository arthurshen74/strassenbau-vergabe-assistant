"""End-to-end ingestion harness for a single ingest job.

Given an existing IngestJob uuid, this drives the whole pipeline against the real services
(Postgres, object storage, Elasticsearch, OpenRouter embeddings + LLM): it marks the job
RUNNING, then renders page thumbnails, extracts SourceLines, simple-chunks every document,
LV-parses an LV document and chunks the resulting LVItems, and finally marks the job DONE
(or FAILED on error). Progress is written to the ingest_job_events table and mirrored to stdout.

The IngestJob, its Document, and the raw PDF in object storage must already exist (they are
created by the upload path), and the LV_EXTRACTION prompt must be seeded
(`python -m scripts.seed.prompts`).

    python -m scripts.run_ingest_job <job_uuid>
"""

from __future__ import annotations

import asyncio
import logging
import sys
from functools import partial
from uuid import UUID

from shared.clients.factory import (
    build_embeddings_client,
    build_llm_client,
    build_telemetry_sinks,
)
from shared.clients.search.client import SearchClient
from shared.clients.storage.client import build_storage_client
from shared.config import settings
from shared.db.engine import make_engine
from shared.db.unit_of_work import unit_of_work
from shared.models.enums import IngestStatus
from shared.repositories.prompt_versions import PromptVersionRepository
from shared.services.ingestion import IngestionService
from shared.services.ingestion.langchain_pipeline import LangchainIngestor
from shared.services.prompt_runner import PromptRunner

logger = logging.getLogger("scripts.run_ingest_job")


async def run_ingest_job(job_uuid: UUID) -> None:
    engine = make_engine(settings.database_url, pool_size=5, application_name="run-ingest-job")
    storage = build_storage_client()
    search = SearchClient.from_settings()
    sinks = build_telemetry_sinks(engine)
    embeddings = build_embeddings_client(sinks, engine)
    llm = build_llm_client(sinks)
    langchain_ingestor = LangchainIngestor(embeddings)
    try:
        await search.ensure_index()

        async with unit_of_work(engine) as uow:
            job = await uow.ingest_jobs.get(job_uuid)
            if job is None:
                raise SystemExit(f"no ingest job {job_uuid}")
            document_uuid = job.document_uuid
            await uow.ingest_jobs.set_status(job_uuid, IngestStatus.RUNNING)
        logger.info("[ingest] job %s RUNNING for document %s", job_uuid, document_uuid)

        # The PromptRunner reads the seeded LV prompt over its own connection; the service's
        # uow_factory opens separate transactional connections per stage.
        async with engine.connect() as prompt_conn:
            prompts = PromptRunner(PromptVersionRepository(prompt_conn), llm)
            service = IngestionService(
                partial(unit_of_work, engine),
                storage,
                search,
                embeddings,
                prompts,
                langchain_ingestor,
            )
            try:
                result = await service.ingest_document(document_uuid, job_uuid=job_uuid)
            except Exception:
                logger.exception("[ingest] job %s FAILED", job_uuid)
                async with unit_of_work(engine) as uow:
                    await uow.ingest_jobs.set_status(job_uuid, IngestStatus.FAILED)
                raise

        async with unit_of_work(engine) as uow:
            await uow.ingest_jobs.set_status(job_uuid, IngestStatus.DONE)
        logger.info(
            "[ingest] job %s DONE: %d source lines, %d thumbnails, %d langchain chunks, "
            "%d document chunks, %d LV items, %d LV chunks",
            job_uuid,
            result.source_lines,
            result.thumbnails,
            result.langchain_chunks,
            result.document_chunks,
            result.lv_items,
            result.lv_chunks,
        )
    finally:
        langchain_ingestor.close()
        await search.close()
        await embeddings.aclose()
        await engine.dispose()


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: python -m scripts.run_ingest_job <job_uuid>")
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stdout,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    asyncio.run(run_ingest_job(UUID(sys.argv[1])))


if __name__ == "__main__":
    main()
