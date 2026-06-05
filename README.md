# Roadbuilders Assistant

A domain-focused RAG system that helps cost calculators (Kalkulatoren) at road-construction
contractors work through public-tender (Vergabe) documents and prepare bids. It ingests a tender's
full document set, builds a structured + vector knowledge base per project, and answers grounded,
citation-backed questions through an agentic chat.

German construction-domain terms used throughout are defined in `GLOSSARY.md`.

## The Problem

A road-construction tender (Straßenbau-Vergabe) ships as a stack of long, cross-referenced documents:
a Baubeschreibung, a Leistungsverzeichnis (LV) with hundreds of priced line items, Vertrags- and
Besondere Vertragsbedingungen, Zusätzliche Technische Vertragsbedingungen (ZTV), a Baugrundgutachten,
sometimes Baupläne and Karten, plus the Vorzulegende Unterlagen the bidder must supply. The ZTV
qualifies items in the LV; the Baubeschreibung constrains how Positionen are priced; gaps in one
document only surface after reading another. Most of the work is retrieval, not judgment. This system
takes the retrieval load off the Kalkulator.

## Architecture at a Glance

- **Backend** — Python 3.12, FastAPI, SQLAlchemy Core (no ORM) + Pydantic v2, asyncpg.
- **Stores** — Postgres (canonical relational data), Elasticsearch (chunk vectors + BM25), MinIO/S3
  (raw PDFs, page thumbnails, rendered maps).
- **Worker** — a competing-consumer ingestion worker that claims jobs with
  `SELECT … FOR UPDATE SKIP LOCKED` and a lease, so multiple workers can run and recover from crashes.
- **LLM access** — all model calls go through an OpenRouter transport; every call is logged
  (tokens/cost/latency) and versioned through the Prompt Library.
- **Frontend** — React + TypeScript (Vite), React Query, Zustand. Types are generated from the backend
  Pydantic DTOs (`ui/src/types/generated.ts`, via `scripts/export_schema.py`).
- **Run** — Docker Compose (postgres, elasticsearch, minio, api, worker, ui).

> **Auth is a development stub.** Every request currently resolves to a single dev administrator
> (`server/api/deps.py`). Real authentication/roles are not implemented.

## What It Does

### Ingestion

A project corresponds to one tender; documents are uploaded to it and ingested by the worker. Every PDF
runs a common stage — text + geometry extraction (`pdftotext -bbox-layout`) into `SourceLine` rows
(the canonical text, so the search index is fully rebuildable) and per-page thumbnails — then branches:

- **All documents** are chunked and embedded into `SimpleChunk`s in Elasticsearch
  (`source_doc_type = DOCUMENT`).
- **LV documents additionally** go through the **LV parse**: an LLM segments the line-numbered text into
  positions, then deterministic code slices the verbatim text, resolves "wie in voriger Position"
  back-references into `langtext_resolved`, links the OZ hierarchy, and writes `LVItem` rows, which are
  chunked into `LV_ITEM` chunks. See `INGESTION.md` and `LV_PARSE.md`.

This supports two retrieval modalities — **Simple** (document chunks) and **Plus** (structured LV items
for the LV, simple chunks for prose).

### Retrieval

RAG retrieval is always project-scoped. Options: **Simple/Plus** modality, **single or multi-query**
(LLM query expansion), optional **BM25** lexical search, and an optional multilingual **cross-encoder**
rerank. Multiple ranked lists are fused with **Reciprocal Rank Fusion (RRF)** before rerank and
top-k selection. See `RETRIEVAL.md`.

### Project Chat

Chat happens in persistent **conversations** with streamed (SSE) turns and replayed history. Each turn
runs an agent that chooses among tools: semantic retrieval over all docs or LV-only, full LV listing,
single-OZ lookup, listing items under a parent OZ, **quantity aggregation** over LV items matching a
free-text predicate, and **map rendering** for a site address. The agent decides which tools to call;
retrieval options above are configurable per turn from the UI.

### Dispatcher

A stateless command bar routes a single instruction to a view: projects, prompts, the prompt-execution
log, the OpenRouter usage log, or the ingest console.

### Prompt Library

Every LLM call is dispatched through a versioned prompt store. A `PromptVersion` is immutable and pins
`prompt_type`, `version`, model, temperature, and sampling settings; creating a new version never
disturbs callers pinned to an older one. Prompts are seeded from `.prompt` files
(`server/scripts/seed/prompts/`) and managed/edited in the UI. Active prompt types: `dispatcher`,
`project_chat`, `lv_extraction`, `aggregate_lv_membership`, `multi_question_generator`,
`conversation_name`. (Response schemas for structured output live in code, not the database.)

### Operational surfaces

- **Prompt execution log** — every LLM call captured with input/output, model, tokens, latency.
- **OpenRouter usage** — per-operation token/cost tracking.
- **Ingest console** — live per-job activity stream, job status, and requeue of stuck jobs.
- **Embedding cache** — optional Postgres-backed cache to avoid re-embedding identical text.

## Getting Started

Runs locally via Docker Compose. Copy `.env.example` to `.env` and fill in an `OPENROUTER_API_KEY`
(plus any other secrets), then:

```
docker compose up --build -d
```

Compose runs the database/storage bootstrap scripts on startup (`server/scripts/bootstrap_*`). The UI
is served on the Vite dev port; the API on port 8000 (`/health/db` for a readiness check).

## Deployment Posture

Single-tenant — each contractor runs its own instance. No multi-tenant isolation is in scope.

## Companion Documents

- `GLOSSARY.md` — German construction-domain terms (LV, GAEB, ZTV, OZ, Vergabe, Kalkulator, …).
- `DATA_SCHEMA.md` — canonical data model: entities, fields, types, enums, cross-store identity.
- `DATA_ARCHITECTURE.md` — SQLAlchemy Core + Pydantic implementation guide for the Postgres layer.
- `INGESTION.md` — the ingestion pipeline.
- `LV_PARSE.md` — the Leistungsverzeichnis parse (companion to `INGESTION.md`).
- `RETRIEVAL.md` — the retrieval pipeline surfaced in Project Chat.
- `UI_WORKFLOW.md` - a workflow diagram for the UI surface.
