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

## The EKT Calculation Agent

A second agent, distinct from Project Chat, turns a single LV Position into a costed estimate. Where
chat answers questions, the calculation agent *produces numbers*: it generates the **EKT** data for a
position.

### What an EKT position is

**EKT** — *Einzelkosten der Teilleistungen* — are the direct costs of one Teilleistung (one LV
Position), broken into four Kostenarten before any overhead, risk, or profit:

- **Lohn** — labour
- **Stoffe** — materials
- **Geräte** — equipment (machines, plant)
- **Sonstiges** — other / third-party (deliveries, quality-assurance tests, Fremdleistungen)

Each per-position EKT also carries a **Zeitansatz** (labour hours per unit). The agent emits one
position's breakdown as a **VHB Formblatt 223**-style row (Aufgliederung der Einheitspreise, *ohne
USt*). The per-unit EKT rolls up into the **Einheitspreis** the bidder enters against that Position in
the Leistungsverzeichnis, and across all positions these breakdowns make up the **Urkalkulation** — the
costing that stands behind the bid.

### Why the calculation is sealed

In a German public tender the priced LV is what the Auftraggeber evaluates, but the underlying
Urkalkulation — captured on the standardised **EFB**-Preis forms, of which the per-position VHB
Formblatt 223 is one — is normally submitted in a **sealed envelope** and left unopened. The
Auftraggeber opens it only in defined circumstances:

- **Preisprüfung of an abnormally low bid** — to test whether a suspiciously low price is *auskömmlich*
  (cost-covering) before the contract may be awarded under "best bid" rules.
- **Nachtragskalkulation** — when scope changes, the unit prices for geänderte oder zusätzliche
  Leistungen (Nachträge) are derived *on the basis of* the original calculation rather than negotiated
  from scratch.
- **Disputes over unit prices** — e.g. price adjustment when executed Mengen deviate from the tendered
  quantities, or other claims where the contractor must evidence the original cost basis.

A clean, defensible per-position breakdown is therefore valuable long after award, not just at bid time.

### The business problem it solves

A road-construction contractor stays in business by keeping a healthy pipeline of *profitable*
projects to bid on, and **cost estimation is the key driver** of that. Inaccurate estimation pushes a
bid the wrong way:

- **Overbidding** loses the award — especially under tightly regulated "best bid" regimes where price
  dominates selection.
- **Underbidding** is doubly dangerous. A bid far below the field can be *excluded* outright as
  abnormally low; a bid that survives the threshold but still under-prices the work turns the project
  into a loss.

The winning posture is an estimate accurate enough to **price risk correctly across the whole scope**.
The most reliable way there is **bottom-up estimation** — building cost up from the scope and the bill
of quantities — and nearly every German road-construction tender ships enough documentation
(Leistungsverzeichnis, Baubeschreibung, ZTV, Baugrundgutachten, plans) to support it. The catch is
time: a single position done by hand can take anywhere from **an hour to half a day**. The agent's goal
is to deliver a detailed, sourced bottom-up EKT breakdown per position in **minutes**. Its target user
is the **Kalkulator** (cost estimator) at the contractor.

### Using the agent

1. **Ingest the project documents.** Upload the tender's documents to the project. A **GAEB file is
   required** — *GAEB 90 (`.d83`)* or *GAEB XML (`.x83`)* — because it is parsed into the structured
   LVItems the calculator costs; prose documents (PDF) supply the surrounding context for retrieval.
2. **Pick a Position and click "Run Calculation".** The button sits on each row of the LV positions
   table, in the position detail dialog, and on the LV result cards in Project Chat. It opens a
   dedicated calculation conversation for that Position's OZ.
3. **Answer the agent when it pauses.** The run is mostly autonomous, but it stops for human input at a
   few points — to confirm which **Leistung** the position is (when classification confidence is low),
   to confirm or correct **driver** values it had to assume, and for a final **review** of the costed
   result before it is committed. When the agent **cannot find a required value** in the documents, it
   surfaces the gap here; the Kalkulator can run a **RAG search** over the project to locate the value
   and feed it back. Corrected values are recorded with full provenance and a confidence of 1.0.
4. **Read the result.** On approval the conversation shows the EKT card — total and per-unit price plus
   the Zeitansatz / Lohn / Stoffe / Geräte / Sonstiges breakdown — and the conversation becomes an
   ordinary project chat thread for follow-up questions.

### How it is built (technical decisions)

The design deliberately separates **LLM judgment** (what the documents say) from **deterministic
computation** (the arithmetic of cost), so that numbers are auditable and never hallucinated.

- **YAML Leistungen registry.** Each supported road-construction service is a versioned YAML file under
  `server/shared/services/calculator/registry/` (currently 11: `fss_herstellen`,
  `asphalttragschicht_herstellen`, `asphalt_fraesen`, `dsk_herstellen`, `planum_herstellen`,
  `boden_verdichten`, `bankett_befestigen`, `bitumenemulsion_aufspruehen`, `asphalteinlage_einbauen`,
  `unterlage_reinigen`, `laengsmarkierung_entfernen`). A registry declares the **drivers** (input facts
  to resolve), **derived drivers** (formulas computed once), and **operations** (the costing procedure,
  with optional Bauweise methods). Adding a Leistung is authoring a file, not changing code.
- **Deterministic Store, with a clean seam to a real one.** Material densities and prices, BGL machine
  rates, performance rates, and labour profiles live in an in-memory Store
  (`server/shared/services/calculator/stores.py`) exposed as named accessor functions that registry
  formulas call by name. This is a stand-in for the firm's golden data (Nachkalkulation, supplier
  quotes, BGL); because every lookup goes through a registered accessor, swapping the dicts for
  versioned database tables is a localised change behind the same interface.
- **Sequential, RAG-based driver lookup.** Drivers are resolved **one at a time**, not in a batch, so a
  human can follow the chain and later drivers can build on earlier ones. Each driver is read from its
  declared source — the LV Langtext directly, or the project documents via the standard retrieval
  pipeline (Plus modality, multi-query, BM25, cross-encoder rerank). Values are **copied verbatim with a
  source quote**; the LLM never computes or invents them. A value that cannot be found does not abort
  the run — it is recorded as a `missing_data` flag and raised in the human review (or earlier, as a
  driver the user must confirm).
- **LangGraph workflow with human-in-the-loop interrupts.** The agent is a LangGraph graph —
  `classify → resolve_drivers → (confirm) → derive → plan/cost operations → aggregate EKT → assess risk
  → review`. The three pause points are real graph `interrupt()`s resumed with `Command(resume=…)`.
  State is checkpointed so a pause survives across HTTP requests: an in-memory `MemorySaver` for the CLI
  harness, and `AsyncPostgresSaver` keyed by the conversation UUID for the API.
- **SSE-streamed reasoning.** The run streams over Server-Sent Events in dual mode — live custom
  reasoning entries as each driver resolves, plus completed-node updates for persistence and to signal
  interrupts — so the long `resolve_drivers` step renders progressively instead of buffering.
- **Form 223 / Kostenart mapping.** Every cost-producing formula maps to exactly one Kostenart
  (`Lohn`/`Stoffe`/`Geräte`/`Sonstiges`); on approval the agent buckets the cost lines, sums labour
  hours into the Zeitansatz, divides by the position quantity, and emits the per-unit `Form223Row`.

> Layering **Allgemeinbaukosten** and **Zuschläge** (the VHB 221/222 overhead and markup that turn the
> EKT into the full Einheitspreis) on top of the breakdown is a deferred follow-up; the agent currently
> produces the per-position 223-style EKT itself.

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
