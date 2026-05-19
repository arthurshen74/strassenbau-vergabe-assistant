# Roadbuilders Assistant

A domain-focused RAG system that helps cost calculators (Kalkulatoren) at road construction contracting companies work through public-tender (Vergabe) documents and prepare bids. The system ingests the full document set for a tender, builds a structured knowledge representation, and answers grounded, citation-backed questions about it.

This README explains what the system is and what it does. Architecture decisions and code-level guidance live in `docs/ARCHITECTURE.md` and `CLAUDE.local.md`. German construction-domain terms used throughout are defined in `docs/GLOSSARY.md`.

## The Problem

A typical road construction tender (Straßenbau-Vergabe) ships as a stack of long, interrelated documents: a Baubeschreibung describing the work, a Leistungsverzeichnis (LV) with hundreds of priced line items, Vertragsbedingungen and Besondere Vertragsbedingungen, Zusätzliche Technische Vertragsbedingungen (ZTV), a Baugrundgutachten, sometimes Baupläne and Karten, plus a list of Vorzulegende Unterlagen the bidder must supply.

A Kalkulator reading this stack has to:

- Decide whether the project is even viable for the company to bid on
- Surface missing information and resolve conflicts between documents
- Assemble cost factors from internal data and subcontractor offers
- Produce a transparent bid that holds up to scrutiny in standard cost-structure review

The documents are long, redundant, and densely cross-referenced. Specifications in the ZTV qualify items in the LV; the Baubeschreibung sets expectations that constrain how individual Positionen are priced; missing details in one document often surface as fatal gaps only after another document is read. Doing this by hand for fifteen tenders in a pipeline is the daily reality, and most of the cognitive load is retrieval, not judgment.

Roadbuilders Assistant exists to take the retrieval load off and let the Kalkulator spend their time on judgment.

## Project Scope

This is **Sprint 2** of a multi-sprint build. The capabilities currently in scope are intentionally narrow: ingest tender documents into a per-project knowledge base, answer chat questions about them with page-level citations, and provide a small set of operational tools. Workflow-deep features — subcontractor outreach, bid assembly, multi-project viability triage — are explicit goals for the Capstone and are not part of the current build.

The Phase Roadmap section below lays out exactly which capabilities ship when.

## Who Uses It

Three user groups, each with a defined permission scope. Permissions are role-based and project-scoped: once a project is ingested, every authorised user of every role can access it. Fine-grained per-user permissioning is a Capstone concern, not a current one.

**Administrator** — manages users, manages projects (create, configure, archive), and ingests data of any type. Effectively a superuser.

**Kalkulator** — creates projects, adds individual documents to existing projects, and queries the system through chat. This is the primary user role.

**Bauleiter** — same as Kalkulator, plus an `ingest_reports` capability for uploading site reports, Bautagebücher, and similar field documents. The Bauleiter role becomes more relevant in later phases when the system supports construction-phase reference.

## What It Does

The system has five functional surfaces.

### 1. Project Ingestion

A project corresponds to one tender. Creating a project means establishing a per-project knowledge base into which the tender documents are ingested. The system ingests three categories of input:

- **GAEB structured exchange files** (D83, X83) — the machine-readable form of the Leistungsverzeichnis. These are parsed into structured LV items carrying OZ (Ordnungszahl), Kurztext, Langtext, Menge, Einheit, and Positionstyp.
- **LV PDFs** — the contractually binding human-readable form of the Leistungsverzeichnis. These are extracted using a vision model so that the structured GAEB items can be linked back to the page they originate from.
- **Prose documents** (Baubeschreibung, Vertragsbedingungen, Besondere Vertragsbedingungen, ZTV, Vorzulegende Unterlagen, and similar) — ingested with a default prose pipeline that decomposes each document into paragraph and table units and downstream assertions or facts.

Project metadata is tracked as a separate, evolving artifact and currently includes at minimum the Vergabe-ID, Auftraggeber, location, Abgabetermin, estimated value, project status, and owning user. The schema is allowed to grow over time.

### 2. Chat

The Kalkulator asks questions about an active project. Answers are RAG-grounded and carry page-level source citations back to the documents in that project's knowledge base. Conversations are scoped to a project, persist across sessions, and are visible to all users with access to that project. Conversations can be exported as Markdown.

### 3. Tools

Three tools are exposed to the chat in the current sprint:

- **LV Item Lookup** — resolve a question about a specific LV item by OZ or description, returning the structured item plus its source page.
- **Ingest Project** — kick off ingestion of a full document set for a new project.
- **Add Document to Project** — append a single document to an existing project's knowledge base.

Tool-call results are surfaced in the chat alongside the assistant's prose response.

### 4. Evaluation

The system ships with an evaluation harness. The eval set itself (target: 50 questions) is authored separately and stored as a project artifact. Each eval record carries:

- `question` — the natural-language query
- `expected_retrieval` — page-level references to the documents that should be retrieved
- `expected_answer` — the ground-truth answer
- `category` — question type (factual lookup, cross-document conflict, calculation, summary, missing-information detection, and so on)
- `difficulty` — easy, medium, or hard
- `scope` — single-document or multi-document
- `tool_call_expectation` — whether the question should trigger a specific tool; tool-call-targeted questions form a distinct eval category

The runner integrates with RAGAs and produces tracked results across runs, supporting comparison between RAG configurations.

### 5. Prompt Library

Every LLM call in the system — vision extraction during ingest, paragraph-to-assertion extraction, chat answer synthesis, eval grading — is dispatched through the **Prompt Library**: a versioned store of system prompts, each pinned to a specific model, temperature, sampling settings, and (where structured output is required) a response schema. Editing a prompt creates a new immutable version; call sites stay on whichever version they reference until explicitly migrated, so a prompt change cannot silently destabilise an upstream pipeline. A small UI surfaces the prompts and their version timelines, and lets authorised users read, edit, and version them.

## Knowledge Representation, at a Glance

The system uses two stores. Neo4j holds the **knowledge graph**: documents, their internal structure, and the relationships between elements. LV items are first-class nodes carrying their structured GAEB attributes; sibling edges (`next_item`, `prev_item`) form a doubly-linked traversal of the LV in original order, and source edges link each item to its corresponding page in the LV PDF. Prose documents decompose into paragraph and table nodes and downstream assertion or fact nodes, with cross-document edges where references warrant.

Postgres holds the **operational data**: project metadata, conversation history, token-usage and cost logs, eval records and run results, and the Prompt Library. Identity (users, roles, OAuth clients, refresh tokens) lives in a separate Postgres database owned by the `auth/` service and is never queried directly by the rest of the system — user identity flows in via OAuth2 tokens.

Detailed schema, modeling decisions, and ingestion pipelines belong in `docs/ARCHITECTURE.md`.

## Phase Roadmap

The capabilities listed below are committed in the noted phase. Anything not listed is out of scope until further notice.

### Current Sprint (Sprint 2)

- Ingest D83 and X83 GAEB files, LV PDFs (vision extraction), and prose tender documents
- Per-project knowledge base in Neo4j and Postgres
- RAG chat with page-level retrieval and page-level source citations
- Three tools: LV Item Lookup, Ingest Project, Add Document to Project
- Authentication and the three-role model (Administrator, Kalkulator, Bauleiter)
- Conversation history per project and Markdown export
- Token usage and cost display, per project
- Eval schema and eval runner integrated with RAGAs
- Prompt Library integration

### Next Sprint (Sprint 3)

- Bautagebuch and site-report ingestion for the Bauleiter role, feeding the same per-project graph
- Shared company-knowledge layer (preferred Lieferanten and Subunternehmer, internal cost-calculation formulas, machine inventory) layered alongside per-project knowledge
- Multi-model support via OpenRouter, selectable per conversation
- Tool-call visualization in the chat UI (inline cards showing tool, input, and output, in the style of Claude.ai)
- Advanced indexing experiments (RAPTOR, ColBERT)

### Capstone

- Subcontractor RFQ generation
- Full bid assembly producing output suitable for transparent cost-structure review
- Viability triage across the active project pipeline
- Per-user-per-project conversation visibility, backed by a permissions table and middleware

## Repository Layout

This is a monorepo with four top-level service or infrastructure directories:

- `ui/` — React and Tailwind frontend, built with the Catalyst UI Kit
- `server/` — Python FastAPI backend (API + ingest worker, shared image)
- `auth/` — OAuth2 Authorization Server, separable from `server/` so it can be replaced by an off-the-shelf component (Ory Hydra, Authentik, Keycloak) without disturbing the rest of the system. `server/` never imports from `auth/`; the contract is HTTP and opaque tokens.
- `docker/` — Docker Compose configuration and supporting infrastructure files

Code-level conventions, internal module structure, and contribution guidance live in `docs/ARCHITECTURE.md` and `CLAUDE.local.md`.

## Getting Started

The system is intended to run locally via Docker Compose and is structured so that the same composition deploys cleanly to a single EC2 instance later.

Local startup, after configuring the environment file (OpenRouter API key, Postgres credentials, Neo4j credentials, and any other required secrets):

```
docker compose up --build -d
```

The first run will build images, bring up Postgres and Neo4j, and start the API and UI services. Initial admin-user creation, seed data, and eval-set loading are handled by separate bootstrap steps documented in `docs/ARCHITECTURE.md`.

## Deployment Posture

Single-tenant. Each contracting company runs its own instance. There is no multi-tenant isolation in scope at any phase of this build.

## Companion Documents

- `docs/GLOSSARY.md` — German construction-domain terms used throughout (LV, GAEB, ZTV, OZ, Vergabe, Auftraggeber, Bauleiter, Kalkulator, Bautagebuch, and others)
- `docs/ARCHITECTURE.md` — system design, data models, ingestion pipelines, retrieval strategy, deployment topology
- `docs/DATA_LAYER_ARCHITECTURE.md` — SQLAlchemy Core + Pydantic implementation guide for the Postgres data layer
- `docs/ORM_OPTIONS.md` — comparison of ORM / Core / SQLModel / Tortoise / roll-your-own that drove the data-layer choice
- `CLAUDE.local.md` — instructions and conventions for AI coding agents working on this codebase
