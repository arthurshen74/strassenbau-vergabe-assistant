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

## 2. Schema layer (`db/tables/`)

The shared `MetaData` + `NAMING_CONVENTION` block is unchanged from the guide. The tables below replace the example ones.

```python
# db/tables/projects.py
from sqlalchemy import Table, Column, Text, DateTime, func, text
from sqlalchemy.dialects.postgresql import UUID

from app.db.metadata import metadata

projects = Table(
    "projects", metadata,
    Column("project_uuid", UUID(as_uuid=True), primary_key=True,
           server_default=text("gen_random_uuid()")),
    Column("vergabe_id", Text, nullable=False),
    Column("project_name", Text, nullable=False),
    Column("project_description", Text, nullable=False),
    Column("vergabestelle", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False,
           server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), nullable=False,
           server_default=func.now(), onupdate=func.now()),
)
```

```python
# db/tables/documents.py
from sqlalchemy import (
    Table, Column, Text, Integer, DateTime, ForeignKey,
    CheckConstraint, func, text,
)
from sqlalchemy.dialects.postgresql import UUID

from app.db.metadata import metadata

documents = Table(
    "documents", metadata,
    Column("document_uuid", UUID(as_uuid=True), primary_key=True,
           server_default=text("gen_random_uuid()")),
    Column("project_uuid", UUID(as_uuid=True),
           ForeignKey("projects.project_uuid", ondelete="CASCADE"),
           nullable=False, index=True),
    Column("document_type", Text, nullable=False),
    Column("file_name", Text, nullable=False),
    Column("document_description", Text, nullable=True),   # marked `?` in DATA_SCHEMA
    Column("number_of_pages", Integer, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False,
           server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), nullable=False,
           server_default=func.now(), onupdate=func.now()),
    # document_type is a closed set in DATA_SCHEMA; enforce it.
    CheckConstraint(
        "document_type IN ('LV_DOCUMENT', 'PROSE_DOCUMENT')",
        name="document_type_valid",  # -> ck_documents_document_type_valid
    ),
)
```

```python
# db/tables/lv_items.py
from sqlalchemy import (
    Table, Column, Text, Integer, Numeric, DateTime,
    ForeignKey, UniqueConstraint, func, text,
)
from sqlalchemy.dialects.postgresql import UUID, ARRAY

from app.db.metadata import metadata

lv_items = Table(
    "lv_items", metadata,
    Column("lv_item_uuid", UUID(as_uuid=True), primary_key=True,
           server_default=text("gen_random_uuid()")),
    Column("document_uuid", UUID(as_uuid=True),
           ForeignKey("documents.document_uuid", ondelete="CASCADE"),
           nullable=False, index=True),
    Column("oz", Text, nullable=False),
    Column("kurztext", Text, nullable=False),
    Column("langtext", Text, nullable=False),
    Column("langtext_resolved", Text, nullable=True),     # `?` — composed only for back-ref items
    Column("menge", Numeric(12, 4), nullable=False),      # Decimal, never float
    Column("einheit", Text, nullable=False),
    Column("positionstyp", Text, nullable=False),         # consider CHECK once value set is pinned
    Column("level", Integer, nullable=False),
    Column("stl_nr", Text, nullable=True),
    Column("hinweis", Text, nullable=True),
    Column("linked_oz", Text, nullable=True),
    Column("prev_oz", Text, nullable=True),
    Column("next_oz", Text, nullable=True),
    Column("parent_oz", Text, nullable=True),
    Column("source_lines", ARRAY(UUID(as_uuid=True)), nullable=False,
           server_default=text("'{}'::uuid[]")),
    Column("last_ingestion", DateTime(timezone=True), nullable=False,
           server_default=func.now(), onupdate=func.now()),
    # (document_uuid, oz) is the composite unique from DATA_SCHEMA (oz unique within a document).
    UniqueConstraint("document_uuid", "oz"),              # -> uq_lv_items_document_uuid
)
```

**Notes**

- `gen_random_uuid()` is built into Postgres 13+ (no `pgcrypto` needed). To get the generated key back on insert, rely on `.returning(...)` in the repository — which the pattern already does.
- `source_lines` as a `uuid[]` array conforms to the schema, but gives up referential integrity and makes "which item owns this line" an array-containment query. The alternative is an `lv_item_uuid` FK on `source_lines`. Either is defensible at tender scale; the schema says array, so this is the array.
- `positionstyp` left as `Text`: its value set (`Normalposition`, `Bedarfsposition`, `Wahlposition`/`Alternativposition`, `Eventualposition`, `Pauschalposition`, `Stundenlohnarbeiten`) is known but the exact stored spelling is the parser's call — add a `CheckConstraint` (or a Postgres enum) once that's fixed.

---

## 3. Domain models (`models/`)

```python
# models/project.py
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class Project(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    project_uuid: UUID
    vergabe_id: str
    project_name: str
    project_description: str
    vergabestelle: str
    created_at: datetime
    updated_at: datetime


class NewProject(BaseModel):
    """Shape required to create a Project. PK and timestamps assigned by DB."""
    model_config = ConfigDict(extra="forbid")

    vergabe_id: str
    project_name: str
    project_description: str
    vergabestelle: str
```

```python
# models/lv_item.py
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class LVItem(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    lv_item_uuid: UUID
    document_uuid: UUID
    oz: str
    kurztext: str
    langtext: str
    langtext_resolved: str | None = None
    menge: Decimal
    einheit: str
    positionstyp: str
    level: int
    stl_nr: str | None = None
    hinweis: str | None = None
    linked_oz: str | None = None
    prev_oz: str | None = None
    next_oz: str | None = None
    parent_oz: str | None = None
    source_lines: list[UUID] = Field(default_factory=list)
    last_ingestion: datetime


class NewLVItem(BaseModel):
    """Shape required to create an LVItem. PK and last_ingestion assigned by DB."""
    model_config = ConfigDict(extra="forbid")

    document_uuid: UUID
    oz: str
    kurztext: str
    langtext: str
    langtext_resolved: str | None = None
    menge: Decimal
    einheit: str
    positionstyp: str
    level: int
    stl_nr: str | None = None
    hinweis: str | None = None
    linked_oz: str | None = None
    prev_oz: str | None = None
    next_oz: str | None = None
    parent_oz: str | None = None
    source_lines: list[UUID] = Field(default_factory=list)
```

---

## 4. API schemas (`models/`, `_schema` suffix)

Suffixes follow the `Create / Read / Update` convention. (DATA_SCHEMA's own examples mix
`ProjectCreateDTO` and `PromptRead` — pick one before generating the whole DTO family.)

```python
# models/project_schema.py
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vergabe_id: str = Field(min_length=1)
    project_name: str = Field(min_length=1)
    project_description: str
    vergabestelle: str


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    project_uuid: UUID
    vergabe_id: str
    project_name: str
    project_description: str
    vergabestelle: str
    created_at: datetime
    updated_at: datetime


class ProjectUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_name: str | None = Field(default=None, min_length=1)
    project_description: str | None = None
    vergabestelle: str | None = None
```

---

## 5. Repository layer (`repositories/`)

The `Project` repository is mechanically identical to the guide's, with `id` → `project_uuid`
and the real fields. The `LVItem` repository is the interesting one — its methods line up with
the two chat gates in the README (`LV_Item_Lookup`, `List_LV_Items_by_Parent_OZ`).

```python
# repositories/lv_items.py
from typing import Sequence
from uuid import UUID

from sqlalchemy import select, insert
from sqlalchemy.ext.asyncio import AsyncConnection

from app.db.tables.lv_items import lv_items
from app.db.tables.documents import documents
from app.domain.lv_item import LVItem, NewLVItem


class LVItemRepository:
    def __init__(self, conn: AsyncConnection):
        self.conn = conn

    async def get(self, lv_item_uuid: UUID) -> LVItem | None:
        row = (await self.conn.execute(
            select(lv_items).where(lv_items.c.lv_item_uuid == lv_item_uuid)
        )).mappings().first()
        return LVItem.model_validate(dict(row)) if row else None

    async def get_by_project_and_oz(self, project_uuid: UUID, oz: str) -> LVItem | None:
        """Backs the LV_Item_Lookup gate. The schema's unique key is (document_uuid, oz),
        so a project+oz lookup resolves through the project's LV document."""
        stmt = (
            select(lv_items)
            .join(documents, documents.c.document_uuid == lv_items.c.document_uuid)
            .where(
                documents.c.project_uuid == project_uuid,
                documents.c.document_type == "LV_DOCUMENT",
                lv_items.c.oz == oz,
            )
        )
        row = (await self.conn.execute(stmt)).mappings().first()
        return LVItem.model_validate(dict(row)) if row else None

    async def list_by_parent_oz(
        self, project_uuid: UUID, parent_oz: str
    ) -> Sequence[LVItem]:
        """Backs the List_LV_Items_by_Parent_OZ gate."""
        stmt = (
            select(lv_items)
            .join(documents, documents.c.document_uuid == lv_items.c.document_uuid)
            .where(
                documents.c.project_uuid == project_uuid,
                documents.c.document_type == "LV_DOCUMENT",
                lv_items.c.parent_oz == parent_oz,
            )
            .order_by(lv_items.c.oz)
        )
        rows = (await self.conn.execute(stmt)).mappings().all()
        return [LVItem.model_validate(dict(r)) for r in rows]

    async def add(self, new: NewLVItem) -> LVItem:
        stmt = insert(lv_items).values(**new.model_dump()).returning(lv_items)
        row = (await self.conn.execute(stmt)).mappings().one()
        return LVItem.model_validate(dict(row))

    async def add_many(self, items: Sequence[NewLVItem]) -> list[LVItem]:
        """Bulk insert for the LV parse output. Relies on SQLAlchemy 2.0
        insertmanyvalues, which supports RETURNING for executemany."""
        if not items:
            return []
        rows = (await self.conn.execute(
            insert(lv_items).returning(lv_items),
            [i.model_dump() for i in items],
        )).mappings().all()
        return [LVItem.model_validate(dict(r)) for r in rows]
```

`select(lv_items).join(documents, ...)` projects only the `lv_items` columns, so the row maps
cleanly onto `LVItem` even under `extra="forbid"`.

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

## 8. FastAPI integration (`api/deps.py`)

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


@router.get("/{project_uuid}", response_model=ProjectRead)
async def read_project(project_uuid: UUID, conn: AsyncConnection = Depends(get_connection)):
    repo = ProjectRepository(conn)
    project = await repo.get(project_uuid)
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

````python
# tests/integration/test_project_repository.py
import pytest
from app.repositories.projects import ProjectRepository
from app.domain.project import NewProject


@pytest.mark.asyncio
async def test_add_and_get(conn):
    repo = ProjectRepository(conn)
    created = await repo.add(NewProject(
        vergabe_id="VG-2026-0042",
        project_name="B247 OD Test",
        project_description="Test tender",
        vergabestelle="LRA Test",
    ))
    fetched = await repo.get(created.project_uuid)
    assert fetched is not None
    assert fetched.project_name == "B247 OD Test"

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
````

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
