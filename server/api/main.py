from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import conversations, health, prompts
from shared.clients.llm.client import LLMClient
from shared.clients.llm.execution_log_sinks import DatabaseExecutionLogSink
from shared.clients.openrouter.usage import DatabaseUsageSink
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
    # One shared LLM client for the process, persisting usage + execution logs to Postgres in
    # their own transactions (independent of any request UnitOfWork).
    app.state.llm_client = LLMClient(
        usage_sink=DatabaseUsageSink(engine),
        execution_log_sink=DatabaseExecutionLogSink(engine),
    )
    try:
        yield
    finally:
        await app.state.llm_client.aclose()
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
    return app


app = create_app()
