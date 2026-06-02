from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import (
    conversations,
    health,
    projects,
    prompt_execution_logs,
    prompts,
    usage,
)
from shared.clients.factory import build_llm_client, build_telemetry_sinks
from shared.clients.search.client import SearchClient
from shared.clients.storage.client import build_storage_client
from shared.config import settings
from shared.db.engine import make_engine


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    engine = make_engine(
        settings.database_url,
        pool_size=10,
        application_name="api",
    )
    app.state.engine = engine
    app.state.storage = build_storage_client()
    app.state.search = SearchClient.from_settings()
    # One shared LLM client for the process, persisting usage + execution logs to Postgres in
    # their own transactions (independent of any request UnitOfWork).
    app.state.llm_client = build_llm_client(build_telemetry_sinks(engine))
    try:
        yield
    finally:
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
    app.include_router(projects.router)
    app.include_router(prompt_execution_logs.router)
    app.include_router(usage.router)
    return app


app = create_app()
