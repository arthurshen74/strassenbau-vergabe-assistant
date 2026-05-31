# SQLAlchemy Core + Pydantic Architecture Guide

A reference architecture for Python + Postgres services using SQLAlchemy Core (no ORM), Pydantic v2 for domain and API models, Alembic for migrations, and asyncpg as the driver. Designed for async services (FastAPI / Litestar) but the same patterns apply synchronously.

The example domain throughout is a small slice of construction project management — `projects`, `estimates`, `line_items` — chosen because it has realistic relationships, JSONB use, and decimal precision concerns.

---

## Architecture at a glance

```
┌─────────────────────────────────────────────────────────┐
│  API layer (FastAPI)                                    │
│  - Pydantic request/response schemas                    │
│  - Routes / dependencies                                │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│  Service layer (optional)                               │
│  - Business logic across multiple repositories          │
│  - Owns transaction boundaries (Unit of Work)           │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│  Repository layer                                       │
│  - One repository per aggregate root                    │
│  - Translates SQLAlchemy Core rows ↔ Pydantic domain    │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│  Persistence layer                                      │
│  - SQLAlchemy Core: Table definitions, MetaData         │
│  - AsyncEngine, connection pool                         │
│  - Alembic migrations (autogenerate as verifier)        │
└─────────────────────────────────────────────────────────┘
                          ↓
                  PostgreSQL (asyncpg)
```

Three Pydantic model families live alongside this:

- **Domain models** (`Project`, `Estimate`, `LineItem`) — the canonical in-memory representation. Repositories return these.
- **API schemas** (`ProjectCreate`, `ProjectRead`, `ProjectUpdate`) — request/response shapes. Derived from domain models or written separately when contracts diverge.
- **Internal DTOs** (rare) — used when a query returns shapes that don't match any domain model (joined views, aggregates).

Keep these separate. The temptation to unify them is exactly what makes SQLModel awkward at scale.

---

## Project Boundaries

Under `/server/shared`, the boundary that matters is between `db/`, `repositories/` and `models/`. The main contract is that db knows nothing about Pydantic domain models (in models) and Pydantic domain models knows nothing about SQLAlchemy. The translation boundary between the two occur in repositories.

---

## 1. Database connection layer (`db/engine.py`)

```python
from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncConnection,
    create_async_engine,
)

from app.config import settings


def make_engine() -> AsyncEngine:
    return create_async_engine(
        settings.database_url,                    # postgresql+asyncpg://...
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,                       # detect dead connections
        pool_recycle=1800,                        # recycle after 30 min
        echo=settings.sql_echo,                   # log SQL in dev
        connect_args={"server_settings": {"application_name": settings.app_name}},
    )


engine: AsyncEngine = make_engine()


@asynccontextmanager
async def connect() -> AsyncIterator[AsyncConnection]:
    """Short-lived connection for a single read or unit of work."""
    async with engine.connect() as conn:
        yield conn


@asynccontextmanager
async def transaction() -> AsyncIterator[AsyncConnection]:
    """Connection wrapped in a transaction; commits on success."""
    async with engine.begin() as conn:
        yield conn
```

**Pool sizing rule of thumb:** `pool_size` ≈ (number of concurrent in-flight requests per worker) × 1.2. `max_overflow` allows bursts. For FastAPI with `--workers 4` and ~25 in-flight requests per worker, `pool_size=10, max_overflow=20` is reasonable. Postgres can usually handle ~100 connections per instance comfortably; size your total across all workers accordingly.

**`pool_pre_ping=True`** costs one `SELECT 1` per checkout but prevents the "stale connection after PgBouncer restart" class of failure. Worth it in any non-trivial deployment.

---

## 2. Schema layer (`db/metadata.py`, `db/tables/`)

A single shared `MetaData` object holds all table definitions and is what Alembic compares against.

```python
# db/metadata.py
from sqlalchemy import MetaData

# Naming convention ensures Alembic-generated constraints have stable names,
# which makes autogenerate migrations diff-clean and prevents random renames.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=NAMING_CONVENTION)
```

```python
# db/tables/projects.py
from sqlalchemy import (
    Table, Column, Integer, BigInteger, String, Text,
    DateTime, ForeignKey, Numeric, JSON,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func
import uuid

from app.db.metadata import metadata

projects = Table(
    "projects", metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column("name", String(255), nullable=False),
    Column("client", String(255), nullable=True),
    Column("status", String(32), nullable=False, server_default="draft"),
    Column("metadata_", JSONB, nullable=False, server_default="{}", key="metadata"),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now(),
           onupdate=func.now()),
)
```

```python
# db/tables/line_items.py
from sqlalchemy import Table, Column, ForeignKey, String, Numeric, Integer
from sqlalchemy.dialects.postgresql import UUID
import uuid

from app.db.metadata import metadata

line_items = Table(
    "line_items", metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column("estimate_id", UUID(as_uuid=True),
           ForeignKey("estimates.id", ondelete="CASCADE"), nullable=False, index=True),
    Column("position_number", String(32), nullable=False),
    Column("description", String, nullable=False),
    Column("quantity", Numeric(12, 4), nullable=False),
    Column("unit", String(16), nullable=False),
    Column("unit_price_cents", Integer, nullable=False),
)
```

**Conventions to follow:**

- Use `UUID` primary keys with `default=uuid.uuid4` (Python-side) rather than autoincrement integers. Avoids exposing row counts, lets you generate IDs before insert, makes merging data across environments safe.
- `server_default` for database-level defaults (`now()`, JSONB `{}`, status enums). `default` is Python-only and won't apply to inserts that bypass the ORM. With Core, you'll often want `server_default` for both consistency and Alembic-detectability.
- `nullable=False` everywhere except where null is semantically meaningful. Don't let nullable creep in by default.
- `ondelete="CASCADE"` on foreign keys when child rows have no meaning without the parent. Otherwise default to `RESTRICT`.
- Store money as `Integer` cents (or `Numeric(12, 2)` if you must), never as `Float`.
- Index foreign keys explicitly (`index=True`). Postgres does not auto-index FKs.
- The `metadata_` column with `key="metadata"` trick: SQLAlchemy attribute names can't be `metadata` (it shadows the Table attribute), but `key="metadata"` lets the Python identifier differ from the column name.

---

## 3. Domain models layer (`models/`)

Pure Pydantic models, no SQLAlchemy imports. These are what the application code passes around.

```python
# models/project.py
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class Project(BaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=False)

    id: UUID
    name: str
    client: str | None = None
    status: str = "draft"
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class NewProject(BaseModel):
    """The shape required to create a new Project. ID and timestamps assigned by DB."""
    name: str
    client: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
```

**`from_attributes=True`** lets you construct these from any object with the right attributes, including SQLAlchemy `Row` objects accessed via `.mappings()`.

**`frozen=False`** is the default; set `frozen=True` if you want immutable domain objects (often a good idea for value objects, less so for entities you update).

Domain models can have methods (calculated properties, validators, business logic). Just don't put persistence concerns in them.

---

## 4. API schemas (`models/`)

These are request/response shapes. Often they overlap with domain models but evolve independently. They will be saved in the same folder as 'models' but they will be named with a `_schema` suffix.

```python
# models/project_schema.py
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    client: str | None = Field(default=None, max_length=255)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    client: str | None
    status: str
    created_at: datetime
    updated_at: datetime


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    client: str | None = None
    status: str | None = None
```

Note `ProjectRead` doesn't expose `metadata` — internal data shouldn't leak through the API by default. This is the kind of separation that breaks down when API and DB schemas are the same class.

---

## 5. Repository layer (`repositories/`)

Repositories are where SQLAlchemy Core meets Pydantic. One repository per aggregate root, holding methods that return domain models.

```python
# repositories/projects.py
from typing import Sequence
from uuid import UUID

from sqlalchemy import select, insert, update, delete
from sqlalchemy.ext.asyncio import AsyncConnection

from app.db.tables.projects import projects
from app.domain.project import Project, NewProject


class ProjectRepository:
    def __init__(self, conn: AsyncConnection):
        self.conn = conn

    async def get(self, id: UUID) -> Project | None:
        row = (await self.conn.execute(
            select(projects).where(projects.c.id == id)
        )).mappings().first()
        return Project.model_validate(dict(row)) if row else None

    async def list(
        self,
        *,
        client: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[Project]:
        stmt = select(projects)
        if client is not None:
            stmt = stmt.where(projects.c.client == client)
        if status is not None:
            stmt = stmt.where(projects.c.status == status)
        stmt = stmt.order_by(projects.c.created_at.desc()).limit(limit).offset(offset)

        rows = (await self.conn.execute(stmt)).mappings().all()
        return [Project.model_validate(dict(r)) for r in rows]

    async def add(self, new: NewProject) -> Project:
        stmt = (
            insert(projects)
            .values(**new.model_dump())
            .returning(projects)
        )
        row = (await self.conn.execute(stmt)).mappings().one()
        return Project.model_validate(dict(row))

    async def update(self, id: UUID, **changes) -> Project | None:
        if not changes:
            return await self.get(id)
        stmt = (
            update(projects)
            .where(projects.c.id == id)
            .values(**changes)
            .returning(projects)
        )
        row = (await self.conn.execute(stmt)).mappings().first()
        return Project.model_validate(dict(row)) if row else None

    async def delete(self, id: UUID) -> bool:
        result = await self.conn.execute(
            delete(projects).where(projects.c.id == id)
        )
        return result.rowcount > 0
```

**Design notes:**

- **Repository takes a connection, not the engine.** This is what enables transaction composition across multiple repositories (see Unit of Work below). It's the single most important architectural choice in this layer.
- **`.mappings()`** gives you dict-like row access. Use it for Pydantic mapping. Without it, you get tuples and have to index by position.
- **`.returning(projects)`** is Postgres-specific (also works in newer SQL Server, etc.) and is the right way to get back the inserted/updated row in one query.
- **No `from_attributes=True` shortcut here** — we use `model_validate(dict(row))` because Row mappings are dict-like but not always picked up by Pydantic's attribute access. Being explicit is safer.

**Optional base class** if you want to factor out the common pattern:

```python
# repositories/base.py
from typing import Generic, TypeVar
from sqlalchemy.ext.asyncio import AsyncConnection
from pydantic import BaseModel

DomainT = TypeVar("DomainT", bound=BaseModel)


class Repository(Generic[DomainT]):
    def __init__(self, conn: AsyncConnection):
        self.conn = conn
```

I'd resist the urge to put generic CRUD methods in the base class. They're rarely reusable in practice because filtering, joining, and projection differ enough per aggregate that the abstraction leaks. Better to write the methods you actually need.

---

## 6. Unit of Work (`db/unit_of_work.py`)

When a single operation spans multiple repositories (create a project AND its initial estimate, atomically), wrap them in a Unit of Work that owns the connection and transaction.

```python
from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncConnection

from app.repositories.projects import ProjectRepository
from app.repositories.estimates import EstimateRepository


class UnitOfWork:
    """Owns a connection and a transaction; exposes repositories that share them."""

    def __init__(self, conn: AsyncConnection):
        self.conn = conn
        self.projects = ProjectRepository(conn)
        self.estimates = EstimateRepository(conn)


@asynccontextmanager
async def unit_of_work(engine: AsyncEngine) -> AsyncIterator[UnitOfWork]:
    async with engine.begin() as conn:           # opens transaction
        yield UnitOfWork(conn)                   # commits on exit, rolls back on exception
```

Usage:

```python
async with unit_of_work(engine) as uow:
    project = await uow.projects.add(NewProject(name="Site A"))
    estimate = await uow.estimates.add_for_project(project.id)
    # both committed atomically
```

For read-only operations, use `engine.connect()` instead of `engine.begin()` — no transaction overhead.

---

## 7. Common query patterns

### Filtering with dynamic conditions

```python
from sqlalchemy import and_, or_

conditions = []
if name_query:
    conditions.append(projects.c.name.ilike(f"%{name_query}%"))
if status:
    conditions.append(projects.c.status == status)
if since:
    conditions.append(projects.c.created_at >= since)

stmt = select(projects)
if conditions:
    stmt = stmt.where(and_(*conditions))
```

`ilike` is Postgres case-insensitive LIKE. The `f"%{name_query}%"` is parametrized — the `f`-string only builds the LIKE pattern; the value is still bound safely.

### Joins

```python
from app.db.tables.estimates import estimates

stmt = (
    select(projects, estimates)
    .select_from(projects.join(estimates, projects.c.id == estimates.c.project_id))
    .where(projects.c.client == "Acme")
)
rows = (await conn.execute(stmt)).mappings().all()
```

When a query returns shapes that don't match a domain model, define a dedicated Pydantic DTO for that query's result rather than trying to force it into existing models.

### Aggregations

```python
from sqlalchemy import func

stmt = (
    select(
        projects.c.client,
        func.count(projects.c.id).label("project_count"),
        func.sum(estimates.c.total_cents).label("total_value_cents"),
    )
    .select_from(projects.join(estimates, projects.c.id == estimates.c.project_id))
    .group_by(projects.c.client)
    .order_by(func.sum(estimates.c.total_cents).desc())
)
```

### JSONB queries

```python
# Find projects where metadata.tags contains "urgent"
stmt = select(projects).where(
    projects.c.metadata["tags"].astext.contains("urgent")
)

# Find by exact JSONB path
stmt = select(projects).where(
    projects.c.metadata["client_data"]["region"].astext == "DE"
)
```

For heavy JSONB use, add a GIN index in the migration: `op.create_index("ix_projects_metadata", "projects", ["metadata"], postgresql_using="gin")`.

### Bulk insert

```python
# Single round-trip, fast
await conn.execute(
    insert(line_items),
    [li.model_dump() for li in many_line_items],
)
```

For very large batches (10k+ rows), drop to asyncpg's `copy_records_to_table` for an order-of-magnitude speedup.

### Pagination (keyset, not offset)

```python
# Keyset pagination — scales to large tables, unlike LIMIT/OFFSET
stmt = (
    select(projects)
    .where(projects.c.created_at < cursor_timestamp)
    .order_by(projects.c.created_at.desc(), projects.c.id.desc())
    .limit(page_size)
)
```

Use `OFFSET` only for small tables or admin views. It's O(offset) on every query and degrades badly past a few thousand rows.

### Soft delete pattern

Add a `deleted_at TIMESTAMPTZ NULL` column. Filter it out by default in the repository:

```python
async def list(self, ..., include_deleted: bool = False):
    stmt = select(projects)
    if not include_deleted:
        stmt = stmt.where(projects.c.deleted_at.is_(None))
    ...
```

---

## 9. FastAPI integration (`api/deps.py`)

```python
from typing import AsyncIterator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncConnection

from app.db.engine import engine
from app.db.unit_of_work import UnitOfWork


async def get_connection() -> AsyncIterator[AsyncConnection]:
    """Read-only connection, no transaction."""
    async with engine.connect() as conn:
        yield conn


async def get_uow() -> AsyncIterator[UnitOfWork]:
    """Transactional unit of work for write operations."""
    async with engine.begin() as conn:
        yield UnitOfWork(conn)
```

Routes:

```python
# api/routes/projects.py
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncConnection

from app.api.deps import get_connection, get_uow
from app.api.schemas.project import ProjectCreate, ProjectRead, ProjectUpdate
from app.db.unit_of_work import UnitOfWork
from app.domain.project import NewProject
from app.repositories.projects import ProjectRepository

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("/{project_id}", response_model=ProjectRead)
async def read_project(project_id: UUID, conn: AsyncConnection = Depends(get_connection)):
    repo = ProjectRepository(conn)
    project = await repo.get(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.post("", response_model=ProjectRead, status_code=201)
async def create_project(body: ProjectCreate, uow: UnitOfWork = Depends(get_uow)):
    return await uow.projects.add(NewProject(**body.model_dump()))
```

Pydantic v2 handles the domain-model → API-schema conversion automatically when you return a `Project` from a route declaring `response_model=ProjectRead`. Both have `model_config = ConfigDict(from_attributes=True)` and overlapping fields.

---

## 10. Testing

### Unit tests for domain logic

Pure Pydantic models with no persistence. Test business rules, validators, calculations. No database needed.

### Integration tests for repositories

Use a real Postgres instance (Docker, ephemeral). Don't mock SQLAlchemy.

```python
# tests/conftest.py
import asyncio
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine

from app.db.metadata import metadata
import app.db.tables  # noqa


@pytest_asyncio.fixture(scope="session")
async def engine():
    engine = create_async_engine("postgresql+asyncpg://test:test@localhost:5433/test")
    async with engine.begin() as conn:
        await conn.run_sync(metadata.drop_all)
        await conn.run_sync(metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def conn(engine):
    """Per-test connection wrapped in a transaction that always rolls back."""
    async with engine.connect() as conn:
        trans = await conn.begin()
        yield conn
        await trans.rollback()
```

The rollback-per-test pattern is fast (no schema reset between tests) and gives perfect isolation.

```python
# tests/integration/test_project_repository.py
import pytest
from app.repositories.projects import ProjectRepository
from app.domain.project import NewProject


@pytest.mark.asyncio
async def test_add_and_get(conn):
    repo = ProjectRepository(conn)
    created = await repo.add(NewProject(name="Test Site"))
    fetched = await repo.get(created.id)
    assert fetched is not None
    assert fetched.name == "Test Site"
```

### End-to-end API tests

Use `httpx.AsyncClient` against the FastAPI app with a test database. Override the `get_connection` and `get_uow` dependencies to use the test engine.

---

## 11. Production concerns

### Connection pool tuning

- `pool_size`: steady-state concurrency per worker
- `max_overflow`: burst capacity
- `pool_timeout`: how long a request waits for a connection before failing (default 30s, often want lower)
- `pool_recycle`: max connection age in seconds (set below your network's idle timeout — AWS NAT is 350s, GCP is often 600s)
- `pool_pre_ping=True`: validates connections on checkout, costs ~1ms

If you front Postgres with PgBouncer in `transaction` pooling mode, set `poolclass=NullPool` on the engine — let PgBouncer do all the pooling.

### Observability

Log slow queries with an engine event listener:

```python
import logging
import time
from sqlalchemy import event
from sqlalchemy.engine import Engine

logger = logging.getLogger("sqlalchemy.slow")
SLOW_QUERY_THRESHOLD = 0.5  # seconds


@event.listens_for(Engine, "before_cursor_execute")
def _before(conn, cursor, statement, parameters, context, executemany):
    context._query_start_time = time.perf_counter()


@event.listens_for(Engine, "after_cursor_execute")
def _after(conn, cursor, statement, parameters, context, executemany):
    elapsed = time.perf_counter() - context._query_start_time
    if elapsed > SLOW_QUERY_THRESHOLD:
        logger.warning("Slow query (%.3fs): %s", elapsed, statement[:200])
```

For deeper observability use OpenTelemetry's SQLAlchemy instrumentation, which produces spans per query and integrates with traces.

### Health checks

```python
@app.get("/health/db")
async def db_health():
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    return {"status": "ok"}
```

### Graceful shutdown

```python
@app.on_event("shutdown")
async def shutdown():
    await engine.dispose()
```

---

## 12. Anti-patterns to avoid

- **Sharing a connection across requests.** Each request gets its own connection from the pool.
- **Holding a transaction open across HTTP boundaries.** Begin and commit inside one request cycle.
- **Repositories that take the engine instead of a connection.** This makes multi-repository transactions impossible.
- **Putting SQLAlchemy types in domain models.** The domain should be ignorant of persistence.
- **Generic CRUD base repositories.** Pleasant in theory, leaky in practice. Write the methods you need.
- **F-string interpolation of values in SQL.** Always parametrize. The `text()` function takes `:name` placeholders; Core takes Python values directly.
- **Mixing `default` and `server_default` on the same column.** Pick one.
- **Skipping `application_name` in connect args.** Without it, you can't tell which service is holding connections in `pg_stat_activity`.

---

## Summary

The architecture is intentionally simple:

1. **Tables** in SQLAlchemy Core, sharing one `MetaData`.
2. **Domain models** in Pydantic, persistence-ignorant.
3. **API schemas** in Pydantic, separate from domain models when contracts diverge.
4. **Repositories** that take a connection and translate Core rows ↔ Pydantic.
5. **Unit of Work** owns the connection and transaction; composes repositories.
6. **FastAPI** wires it together with two dependencies: read-only connection or transactional UoW.

What you give up versus a full ORM: relationship loaders, identity map, lazy/eager loading machinery, hybrid properties, declarative inheritance. What you keep: parametrized query composition, migrations, connection pooling, type adaptation, async, the full Postgres dialect, and your sanity.
