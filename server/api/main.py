from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from api.routes import (
    calculations,
    conversations,
    dispatch,
    eval_runs,
    ground_truth,
    health,
    ingest_jobs,
    katalog,
    project_contexts,
    projects,
    prompt_execution_logs,
    prompts,
    rag_ground_truth,
    usage,
)
from shared.clients.factory import (
    build_embeddings_client,
    build_llm_client,
    build_rerank_client,
    build_telemetry_sinks,
)
from shared.clients.search.client import SearchClient
from shared.clients.storage.client import build_storage_client
from shared.clients.tracing import setup_phoenix_tracing
from shared.config import settings
from shared.db.engine import make_engine
from shared.services.kalkulation_v2.provider import lade_katalog

# Connection pool for the calculator's LangGraph Postgres checkpointer (HITL state across requests).
CALCULATOR_CHECKPOINTER_POOL_SIZE = 10

# Phoenix project the API process reports its traces under.
PHOENIX_PROJECT_NAME = "roadbuilders-api"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Install OTLP tracing before any client is built so every LangChain/LangGraph run is captured.
    setup_phoenix_tracing(PHOENIX_PROJECT_NAME)
    engine = make_engine(
        settings.database_url,
        pool_size=10,
        application_name="api",
    )
    app.state.engine = engine
    # Load the persisted catalog into the kalkulation_v2 module dicts before serving. A dev DB
    # without seed logs a warning and keeps the fixture data, so startup never crashes.
    async with engine.connect() as conn:
        await lade_katalog(conn)
    app.state.storage = build_storage_client()
    app.state.search = SearchClient.from_settings()
    # One shared telemetry-sink set per process, reused by every OpenRouter client so usage +
    # execution logs land in Postgres the same way (in their own transactions, independent of any
    # request UnitOfWork). The embeddings + reranker clients back project-chat RAG retrieval.
    sinks = build_telemetry_sinks(engine)
    app.state.telemetry_sinks = sinks
    app.state.llm_client = build_llm_client(sinks)
    app.state.embeddings = build_embeddings_client(sinks, engine)
    app.state.reranker = build_rerank_client(sinks)
    # The EKT calculator persists its LangGraph state across HITL interrupts in Postgres so a run can
    # pause for the Kalkulator and resume in a later request. It uses its own psycopg pool (the libpq
    # driver), separate from the SQLAlchemy/asyncpg engine. The DSN drops the asyncpg driver suffix.
    checkpointer_pool = AsyncConnectionPool(
        conninfo=settings.database_url.replace("+asyncpg", ""),
        max_size=CALCULATOR_CHECKPOINTER_POOL_SIZE,
        open=False,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
    )
    await checkpointer_pool.open()
    checkpointer = AsyncPostgresSaver(checkpointer_pool)
    await checkpointer.setup()
    app.state.calculator_checkpointer = checkpointer
    app.state.calculator_checkpointer_pool = checkpointer_pool
    try:
        yield
    finally:
        await app.state.calculator_checkpointer_pool.close()
        await app.state.reranker.aclose()
        await app.state.embeddings.aclose()
        await app.state.llm_client.aclose()
        await app.state.search.close()
        await engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(title="Roadbuilders Assistant API", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    app.include_router(prompts.router)
    app.include_router(conversations.router)
    app.include_router(dispatch.router)
    app.include_router(projects.router)
    app.include_router(project_contexts.router)
    app.include_router(prompt_execution_logs.router)
    app.include_router(usage.router)
    app.include_router(ingest_jobs.router)
    app.include_router(calculations.router)
    app.include_router(katalog.router)
    app.include_router(ground_truth.router)
    app.include_router(rag_ground_truth.router)
    app.include_router(eval_runs.router)
    return app


app = create_app()
