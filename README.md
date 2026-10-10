# Roadbuilders Assistant

A domain-focused RAG system that helps cost calculators (Kalkulatoren) at road-construction
contractors work through public-tender (Vergabe) documents and prepare bids. It ingests a tender's
full document set, builds a structured + vector knowledge base per project, answers grounded,
citation-backed questions through an agentic chat, and produces auditable per-position cost
estimates (EKT).

German construction-domain terms used throughout are defined in `GLOSSARY.md`.

## The Problem

A road-construction tender (Straßenbau-Vergabe) ships as a stack of long, cross-referenced documents:
a Baubeschreibung, a Leistungsverzeichnis (LV) with hundreds of priced line items, Vertrags- and
Besondere Vertragsbedingungen, Zusätzliche Technische Vertragsbedingungen (ZTV), a Baugrundgutachten,
sometimes Baupläne and Karten, plus the Vorzulegende Unterlagen the bidder must supply. The ZTV
qualifies items in the LV; the Baubeschreibung constrains how Positionen are priced; gaps in one
document only surface after reading another. Most of the work is retrieval, not judgment. This system
takes the retrieval load off the Kalkulator.

## What It Does

### Ingestion

A project corresponds to one tender; documents are uploaded to it and ingested by a background
worker. Every PDF is extracted into canonical per-line text (so the search index is always
rebuildable), rendered into page thumbnails, and chunked and embedded for semantic search. The
structured LV comes from the tender's **GAEB file** (`.d83` or `.x83`), which parses
deterministically — no LLM — into LV positions with resolved back-references ("wie in voriger
Position"), the Hinweise in each position's scope, the full OZ hierarchy, and the LV-level
Vorbemerkungen/Nachtext (GAEB 90 T-lines, GAEB XML `AddText`). Each uploaded GAEB file becomes
its own LV document, so a project can carry several (e.g. one per Los); re-ingestion archives prior
search data instead of overwriting it.

### Retrieval

RAG retrieval is always project-scoped. Options, configurable per chat turn: **Simple/Plus**
modality (Plus represents the LV structurally by its parsed positions), **single or multi-query**
(LLM query expansion), optional **BM25** lexical search, and an optional multilingual
**cross-encoder** rerank. Multiple ranked lists are fused with Reciprocal Rank Fusion before
top-k selection.

### Project Chat

Chat happens in persistent **conversations** with streamed (SSE) turns and replayed history. Each
turn runs an agent that chooses among tools: semantic retrieval over all docs or LV-only, full LV
listing, single-OZ lookup, listing items under a parent OZ, **quantity aggregation** over LV items
matching a free-text predicate, and **map rendering** for a site address. Answers carry numbered
citations back to the source passages.

### Dispatcher

A stateless command bar routes a single instruction to a view: projects, prompts, the
prompt-execution log, the OpenRouter usage log, or the ingest console.

### The Katalog

The calculator's reference data — Leistungen, recipes, machines, materials, suppliers and their
prices, formulas — lives in a versioned catalog with a draft/active lifecycle. A dedicated
**Katalog chat** agent browses and edits it conversationally: it drafts validated change bundles,
but only a human can activate them. The **recipe compiler** drafts a whole new Leistung (recipe,
operations, formulas, variables) from a Kalkulator's free-text description, justifying what it
reused versus minted.

### Prompt Library

Every persistent LLM prompt is versioned and immutable: a new version never disturbs callers of an
older one. Prompts are seeded from files and managed in the UI, so prompt changes are deployable
and diffable.

### Operational surfaces

- **Prompt execution log** — every LLM call captured with input/output, model, tokens, latency.
- **OpenRouter usage** — per-operation token/cost tracking.
- **Ingest console** — live per-job activity stream, job status, and requeue of stuck jobs.
- **Eval workspace** — golden data curation and evaluation runs with live progress
  (see `AI_EVALUATION.md`).
- **Phoenix traces** — every LLM call and agent flow, grouped per conversation.

## The EKT Calculation Agent

A second agent, distinct from Project Chat, turns a single LV Position into a costed estimate. Where
chat answers questions, the calculation agent _produces numbers_: it generates the **EKT** data for a
position.

### What an EKT position is

**EKT** — _Einzelkosten der Teilleistungen_ — are the direct costs of one Teilleistung (one LV
Position), broken into four Kostenarten before any overhead, risk, or profit:

- **Lohn** — labour
- **Stoffe** — materials
- **Geräte** — equipment (machines, plant)
- **Sonstiges** — other / third-party (deliveries, quality-assurance tests, Fremdleistungen)

Each per-position EKT also carries a **Zeitansatz** (labour hours per unit). The agent emits one
position's cost breakdown with a complete derivation trail — every value with its source and
evidence (the Nachweistabelle); rendering it as the **VHB Formblatt 223** row (Aufgliederung der
Einheitspreise, _ohne USt_) is a planned enhancement. The per-unit EKT rolls up into the
**Einheitspreis** the bidder enters against that Position in the Leistungsverzeichnis, and across
all positions these breakdowns make up the **Urkalkulation** — the costing that stands behind the
bid.

### Why the calculation is sealed

In a German public tender the priced LV is what the Auftraggeber evaluates, but the underlying
Urkalkulation — captured on the standardised **EFB**-Preis forms, of which the per-position VHB
Formblatt 223 is one — is normally submitted in a **sealed envelope** and left unopened. The
Auftraggeber opens it only in defined circumstances:

- **Preisprüfung of an abnormally low bid** — to test whether a suspiciously low price is _auskömmlich_
  (cost-covering) before the contract may be awarded under "best bid" rules.
- **Nachtragskalkulation** — when scope changes, the unit prices for geänderte oder zusätzliche
  Leistungen (Nachträge) are derived _on the basis of_ the original calculation rather than negotiated
  from scratch.
- **Disputes over unit prices** — e.g. price adjustment when executed Mengen deviate from the tendered
  quantities, or other claims where the contractor must evidence the original cost basis.

A clean, defensible per-position breakdown is therefore valuable long after award, not just at bid time.

### The business problem it solves

A road-construction contractor stays in business by keeping a healthy pipeline of _profitable_
projects to bid on, and **cost estimation is the key driver** of that. Inaccurate estimation pushes a
bid the wrong way:

- **Overbidding** loses the award — especially under tightly regulated "best bid" regimes where price
  dominates selection.
- **Underbidding** is doubly dangerous. A bid far below the field can be _excluded_ outright as
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
   required** — _GAEB 90 (`.d83`)_ or _GAEB XML (`.x83`)_ — because it is parsed into the structured
   LV positions the calculator costs; prose documents (PDF) supply the surrounding context for
   retrieval.
2. **Pick a Position and click "Position Chat".** The button sits on each row of the LV positions
   table, in the position detail dialog, and on the LV result cards in Project Chat. It opens a
   dedicated calculation conversation for that Position's OZ.
3. **Answer the agent at its four gates.** The run is autonomous between gates, streams its
   reasoning live, and pauses for a structured decision at each of four points: **project context**
   (confirm the Baustelle, Deponie, and site parameters — with rendered site and route maps; values
   confirmed here carry over to every other position in the project), **method** (confirm the
   classified Leistung, pick the Bauverfahren), **material** (confirm the matched Baustoff, where
   the recipe consumes one), and the **variable review** (every value the calculation will consume,
   with source and confidence — low-confidence and high-stakes values surfaced for explicit
   decision, the rest pre-accepted but overridable; machine and supplier picks sit in the same
   form). Values the Kalkulator already stated in chat are picked up automatically and skip the
   search. Corrections are recorded with full provenance, and a reviewed position can be saved as
   evaluation gold in one click.
4. **Read the result.** On approval the conversation shows the EKT card — total and per-unit price
   with the cost lines per operation and Kostenart — plus the Nachweistabelle showing how every
   number was derived, and a short narration. The conversation then becomes an ordinary project
   chat thread for follow-up questions.

How the agent is built — the deterministic calculation engine, the catalog spine, the LangGraph
gate flow — is documented in `AI_ARCHITECTURE.md`.

> Layering the **Zuschläge** — Baustellengemeinkosten, Allgemeine Geschäftskosten, Wagnis und
> Gewinn (VHB Formblätter 221/222), which turn the EKT into the full Einheitspreis — on top of the
> breakdown is a deferred follow-up; the agent currently produces the per-position EKT itself.

## Architecture at a Glance

- **Backend** — Python 3.12, FastAPI, SQLAlchemy Core (no ORM) + Pydantic v2, asyncpg.
- **Stores** — Postgres (canonical relational data), Elasticsearch (chunk vectors + BM25), MinIO/S3
  (raw PDFs, thumbnails, rendered maps).
- **Worker** — a competing-consumer process (ingestion + eval runs) that scales horizontally;
  Postgres allocates jobs via `SKIP LOCKED` leases.
- **LLM access** — all model calls go through an OpenRouter transport; every call is logged
  (tokens/cost/latency) and versioned through the Prompt Library; traces land in Phoenix.
- **Frontend** — React 19 + TypeScript (Vite), React Query, Zustand. Types are generated from the
  backend Pydantic DTOs.

> **Auth is a development stub.** Every request currently resolves to a single dev administrator.
> Real authentication/roles are not implemented — see `DATA_GOVERNANCE.md` before deploying
> anywhere reachable.

The full picture — layers, data model with ERD, worker mechanics, frontend structure — is in
`APPLICATION_ARCHITECTURE.md`.

## Getting Started

Prerequisites: Docker with Compose, an [OpenRouter](https://openrouter.ai) API key, and optionally
a Google Maps API key (site/route maps and supplier-distance ranking degrade without it).

```bash
# 1. Configure
cp .env.example .env    # set OPENROUTER_API_KEY (+ GOOGLE_STATIC_MAPS_API_KEY, optional);
                        # Postgres/MinIO credentials ship with dev defaults — change for real use

# 2. Start — the api container bootstraps databases, tables, and the bucket on first run
docker compose up --build -d

# 3. Seed the prompt library and the calculation catalog (once)
docker compose exec api python -m scripts.seed.prompts
docker compose exec api python -m scripts.seed.seed_katalog
```

Then open:

- **UI** — <http://localhost:5173>
- **API docs (OpenAPI)** — <http://localhost:8000/docs> (`/health/db` for readiness)
- **Phoenix traces** — <http://localhost:6006> · **MinIO console** — <http://localhost:9001>

**First project:** there are two ways to create one under Projects.

- **Ingest Project from ZIP** — upload the tender ZIP as downloaded from the Vergabeplattform. The
  project is named after the ZIP, and every PDF and GAEB file (`.x83`, `.d83`) inside it, nested
  ZIPs included, is queued for ingestion; each GAEB file becomes its own LV document. Files of
  other types are listed on the project page as not ingested.
- **Ingest New Project** — fill in the project form, then upload the tender's GAEB file plus its
  PDFs (or a ZIP of them) with **Ingest New Document**.

Either way, watch ingestion on the project's Documents tab or in the ingest console. Then ask
questions in Project Chat, open the LV table, and
click **Position Chat** on a position to walk the four gates to a costed EKT. You can find project tender documents at some of the following websites:

- [E-Vergabe Online](https://www.evergabe-online.de/start.html?0)
- [E-Vergabe Simple Search](https://www.evergabe-online.de/search.html?1)

## For Devs

Suggested reading order:

1. **`APPLICATION_ARCHITECTURE.md`** — processes, layers, data model (ERD), worker, frontend.
2. **`AI_ARCHITECTURE.md`** — ingestion, retrieval, the three agents with state diagrams, prompt
   and model management.
3. **`AI_EVALUATION.md`** — failure modes, graders, golden data, current baselines, how to run
   evals.
4. **`DEVOPS.md`** — full configuration reference, operations, scaling, backups, production
   hardening.
5. **`DATA_GOVERNANCE.md`** — data inventory, external data flows, retention, sensitivity posture.

`GLOSSARY.md` defines the German domain terms all of these use. Development basics: dependencies
via `uv sync` (backend, from the repo root) and `npm install` (in `ui/`); tests with
`uv run pytest`; UI dev server with `npm run dev`; regenerate the TypeScript API types with
`npm run gen:types` after changing backend DTOs.
