# DevOps

Running the system for real: configuration, operations, scaling, and the gap between the current
development posture and production. The README's Getting Started section covers the local run;
this document covers everything after that. Deployment model: **single-tenant** — each contractor
runs its own instance; multi-tenant isolation is explicitly out of scope.

## Services and Topology

Docker Compose runs seven services. The `api` container executes the bootstrap scripts before
starting the server, so a first `docker compose up --build -d` on an empty machine converges to a
working stack.

| Service | Image | Ports | Data | Notes |
| --- | --- | --- | --- | --- |
| `postgres` | `postgres:latest` | 5432 | `data/postgres` | Health: `pg_isready`. The `sql/` directory is mounted at `/sql` for ad-hoc DDL. |
| `elasticsearch` | `elasticsearch:8.15.0` | 9200 | `data/elasticsearch` | Single node, security and TLS disabled, 2 GB heap. |
| `minio` | `minio/minio` | 9000 (S3), 9001 (console) | `data/minio` | Bucket created by bootstrap. |
| `phoenix` | `arizephoenix/phoenix` | 6006 (UI + HTTP OTLP), 4317 (gRPC OTLP) | `data/phoenix` | LLM/agent trace collector. |
| `api` | `server/Dockerfile` | 8000 | — | Runs `bootstrap_dbs && bootstrap_tables && bootstrap_storage`, then uvicorn with `--reload` on the bind-mounted source. Health: `/health/db` (30 s start period). |
| `worker` | `server/Dockerfile` | — | — | `python -m worker.main`; `restart: unless-stopped`; deliberately no `container_name` so `--scale worker=N` works. |
| `ui` | `ui/Dockerfile` | 5173 | — | Vite dev server proxying `/api/*` to the api service. |

Startup ordering is encoded in `depends_on`: api and worker wait for healthy Postgres and
Elasticsearch. The store volumes are bind mounts under `data/`.

## Configuration Reference

All settings load from the repo-root `.env` via one pydantic-settings class
(`server/shared/config.py`). Env var name = field name uppercased; unknown variables are ignored.
Copy `.env.example` to `.env` to start.

**Required, no default (the stack will not start without them):**

| Variable | Meaning |
| --- | --- |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` | Postgres superuser credentials (also consumed by the postgres container). |
| `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` | MinIO credentials; doubles as the S3 access/secret key pair. |

**Secrets, optional (features degrade without them):**

| Variable | Default | Meaning |
| --- | --- | --- |
| `OPENROUTER_API_KEY` | — | All LLM traffic: chat, embeddings, rerank. Without it, ingestion embedding and every agent fail. |
| `GOOGLE_STATIC_MAPS_API_KEY` | — | Geocoding, route matrices, static maps (project context Gate 1, supplier ranking, `render_map`). |
| `ANTHROPIC_API_KEY` | — | Only the dev-time RAG ground-truth generator (`eval/generator/`). Not needed to run the product. |
| `JWT_SECRET` | — | Reserved for the planned auth stack; unused today. |

**Connections and stores:**

| Variable | Default |
| --- | --- |
| `POSTGRES_DB` | `roadbuilders` (bootstrap also derives `{db}_auth` and `{db}_test`) |
| `POSTGRES_HOST` / `POSTGRES_PORT` | `localhost` / `5432` (compose overrides host to the service name) |
| `S3_HOST` / `S3_PORT` / `S3_BUCKET` | `localhost` / `9000` / `roadbuilders` |
| `ELASTICSEARCH_HOST` / `ELASTICSEARCH_PORT` | `localhost` / `9200` |
| `ELASTICSEARCH_INDEX` | `roadbuilders_text` (+ derived `_archive`) |
| `LANGCHAIN_INDEX` | `idx-langchain-roadbuilders` |
| `PHOENIX_COLLECTOR_ENDPOINT` | `http://localhost:6006/v1/traces` |

**Models and retrieval:**

| Variable | Default |
| --- | --- |
| `EMBEDDING_MODEL` / `EMBEDDING_DIM` | `openai/text-embedding-3-small` / `512` |
| `EMBEDDING_CACHE_ENABLED` | `true` (Postgres-backed embedding cache) |
| `CROSS_ENCODER_MODEL` | `cohere/rerank-4-fast` |
| `MULTI_QUERY_N` | `5` |
| `RETRIEVER_CANDIDATE_K` / `RETRIEVER_TOP_K` | `50` / `10` |
| `CALCULATOR_MODEL` / `KATALOG_CHAT_MODEL` | `openai/gpt-5.4` |
| `CALCULATOR_REASONING_EFFORT` | `low` |
| `CALCULATOR_MOCK` | `false` (canned LLM replies for offline runs) |
| `KATALOG_CHAT_TEMPERATURE` | unset |
| `OPENROUTER_API_URL_CHAT` / `_EMBEDDING` / `_RERANK` | OpenRouter endpoints |

**Calculator tuning:**

| Variable | Default |
| --- | --- |
| `CALCULATOR_BAUSTOFF_MATCH_THRESHOLD` | `0.6` (BM25 auto-apply confidence for material matching) |
| `CALCULATOR_MASCHINE_ZIELSTUNDEN` | `16.0` (machine right-sizing target hours) |
| `CALCULATOR_LIEFERANT_RADIUS_KM` | `100.0` (supplier pre-filter radius) |
| `CALCULATOR_HGV_DETOUR_FACTOR` | `1.0` (HGV correction on routed distances) |
| `STATIC_MAP_ZOOM` / `MAPS_REQUEST_TIMEOUT_SECONDS` | `12` / `20.0` |
| Google Maps endpoint URLs | overridable, default to the public APIs |

**Worker and activity stream:**

| Variable | Default |
| --- | --- |
| `WORKER_POLL_INTERVAL_SECONDS` | `2.0` |
| `WORKER_LEASE_SECONDS` | `60.0` (job lease; heartbeats must land inside it) |
| `WORKER_MAX_ATTEMPTS` | `3` (then the job parks as failed) |
| `ACTIVITY_FLUSH_SECONDS` | `1.0` (activity buffer flush = lease heartbeat; keep well below the lease) |
| `ACTIVITY_THUMBNAIL_EVERY` / `ACTIVITY_EMBED_EVERY` / `ACTIVITY_LV_ITEM_EVERY` | `10` / `10` / `1` (progress-line granularity) |
| `ACTIVITY_RETENTION_HOURS` | `24` (hot activity log before archive) |
| `INGEST_STATUS_POLL_INTERVAL_SECONDS` | `1.5` (SSE status stream poll) |

Connection URLs (domain/auth/test database, Elasticsearch, S3 endpoint) are derived properties —
never set them directly.

## Bootstrap, Migrations, and Seeding

Three idempotent bootstrap scripts run on api start (or manually via
`uv run python -m scripts.bootstrap_*`):

1. `bootstrap_dbs` — creates the three databases if absent: the domain DB, `{db}_auth`
   (provisioned for the future auth stack), `{db}_test` (integration tests).
2. `bootstrap_tables` — registers all Core tables and runs `metadata.create_all` (checkfirst) on
   the domain DB. **There is no migration tool**: `create_all` only adds missing tables, it never
   alters existing ones. Schema changes on a populated database currently mean hand-written DDL
   (the `sql/` directory, mounted into the Postgres container) — adopting Alembic is on the
   enhancement list.
3. `bootstrap_storage` — creates the MinIO bucket (retries up to 60 s while MinIO starts).

Elasticsearch indexes are not bootstrapped — the search client ensures them at runtime.

Seeding, run once after first boot:

```bash
PYTHONPATH=server uv run python -m scripts.seed.prompts        # prompt library
PYTHONPATH=server uv run python -m scripts.seed.seed_katalog   # calculation catalog
```

The two behave differently by design. **Prompt seeding is append-only and not idempotent**: every
run publishes a new version of every `.prompt` file, and the application reads the latest — this
is also the mechanism for shipping prompt changes. **Katalog seeding is guarded**: it aborts if
any catalog table has rows; `--reset` truncates and reseeds. Type generation for the UI
(`npm run gen:types`) reruns whenever backend DTOs change.

## Scaling

Ingestion and eval throughput scale horizontally: `docker compose up --scale worker=N`. Workers
compete for jobs on both queues via `SELECT … FOR UPDATE SKIP LOCKED` — Postgres is the allocator,
there is no dispatcher, and a crashed worker's jobs are reclaimed by lease expiry (see
`APPLICATION_ARCHITECTURE.md`).

What does not scale horizontally yet: the API is one process (uvicorn, no worker fan-out
configured), Elasticsearch is a single node, Postgres is one instance. Watch the connection
budget when scaling workers: the api engine holds up to 20 connections (pool 10 + overflow),
each worker up to 10 (pool 5 + overflow), plus the api's separate checkpointer pool (10).

External rate limits are the practical ceiling before infrastructure is: every LLM, embedding,
and rerank call goes through OpenRouter, and ingestion of a large document set is
embedding-heavy. The Postgres embedding cache absorbs re-ingestion of identical text.

## Observability and Operations

- **Health** — `GET /health` (liveness), `GET /health/db` (readiness; used by the compose
  healthcheck).
- **Phoenix** (`localhost:6006`) — OTLP traces for every LLM call and agent flow, grouped per
  conversation via session ids. Traces include full prompts and completions; treat the Phoenix
  volume with the same confidentiality as the database.
- **Prompt execution log** (UI, `/execlog`) — every LLM call with full request/response, tokens,
  latency, and success flag.
- **OpenRouter usage** (UI, `/usagelog`) — per-call cost in USD-denominated credits, attributable
  to project/conversation/ingest job.
- **Ingest console** (UI, `/ingestlog`) — live per-job activity stream over SSE, job statuses, and
  one-click requeue of stuck or failed jobs (safe: ingestion is idempotent).
- **Eval runs** (UI, per-project eval workspace) — queue state, live progress events, per-item
  results.
- **Container logs** — `docker compose logs -f api worker`; the backend logs one line per failure
  at the boundary, with request ids surfaced to the UI via the `X-Request-Id` header.

## Backups and Data Durability

What must be backed up:

- **Postgres `data/postgres`** — the canonical store: projects, documents' extracted text, LV
  items, conversations, the Katalog, gold data, logs.
- **MinIO `data/minio`** — the only copy of the original uploaded PDFs (plus thumbnails and
  rendered maps, which are re-derivable from the PDFs).

What is rebuildable and needs no backup: both Elasticsearch indexes (re-ingestion replays from
Postgres `source_lines`/`lv_items`; costs embedding calls unless cached) and the Phoenix trace
volume (operational telemetry). The `{db}_test` database is disposable.

Consistency note: a Postgres backup and a MinIO backup taken together are sufficient to rebuild
everything; there is no state anywhere else.

## Production Hardening Checklist

The compose file is a development topology. An implementer taking this to production closes, at
minimum:

- **Authentication** — every request currently acts as one fixed administrator; network-level
  access control is the only boundary. The fastapi-users plan is in
  `APPLICATION_ARCHITECTURE.md`'s Future Enhancements.
- **CORS** — hardcoded to the Vite dev origin (`http://localhost:5173`); must match the real UI
  origin.
- **UI serving** — the UI runs on the Vite dev server; production needs `npm run build` and a
  static server / reverse proxy.
- **API server** — uvicorn runs with `--reload` on bind-mounted source; production wants a fixed
  image, no reload, and a process manager or multiple workers.
- **TLS and proxying** — nothing terminates TLS; a reverse proxy in front of api and ui is
  expected. Mind SSE when configuring it: response buffering and compression must be off for the
  streaming endpoints.
- **Elasticsearch security** — xpack security and TLS are disabled for the single-node dev setup.
- **Exposed ports** — Postgres, Elasticsearch, and MinIO publish their ports to the host; bind
  them to localhost or drop the mappings in production.
- **Secrets** — a flat `.env` file; move to a secrets manager as appropriate.
- **Image pinning** — `postgres:latest` and `arizephoenix/phoenix:latest` are unpinned; pin
  versions for reproducible deployments.
- **Schema migrations** — no migration tool yet; see Bootstrap above.

## API Reference

FastAPI serves the interactive OpenAPI documentation at `http://localhost:8000/docs` (schema at
`/openapi.json`). The same Pydantic DTOs generate the UI's TypeScript types via
`scripts/export_schema.py`, so the OpenAPI schema is authoritative for integration work.
