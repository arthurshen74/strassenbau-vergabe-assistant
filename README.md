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

A project corresponds to one tender. Creating a project means establishing a per-project knowledge base into which the tender documents are ingested. The system ingests two categories of input:

- **LV PDFs** — the contractually binding human-readable form of the Leistungsverzeichnis. These are parsed deterministically from the embedded PDF text layer (pdfplumber), with vision used only as a fallback for pages that lack a usable text layer; each LV Position is linked back to its source page.
- **Prose documents** (Baubeschreibung, Vertragsbedingungen, Besondere Vertragsbedingungen, ZTV, Vorzulegende Unterlagen, and similar) — ingested with a default prose pipeline that decomposes each document into two parallel chunk sets (`SimpleChunk`, fixed-size; and `ProseChunk`, section-aware). Paragraph/assertion extraction is deferred to a later sprint.

### 2. Chat

The Kalkulator asks questions about an active project. Answers are RAG-grounded and carry page-level source citations back to the documents in that project's knowledge base. Conversations are scoped to a project, persist across sessions, and are visible to all users with access to that project. Conversations can be exported as Markdown.

### 3. Tools

Three tools are exposed to the chat in the current sprint:

- **LV Item Lookup** — the user can look up a specific LV Item. resolve a question about a specific LV item by OZ or description, returning the structured item plus its source page.
- **Ingest Project** — kick off ingestion of a full document set for a new project.
- **Add Document to Project** — append a single document to an existing project's knowledge base.
- **Add Project** - create a new project, ostensibly to ingest project documents.
- **View Prompts** - list prompts in the system.

Tool-call results are surfaced ON TOP of the chat interface as a modal dialog. The chat has two modalities:

- Dispatch: the primary default modality, where the tool calls surface the component dialogs.
- Discuss Project: when a user selects a project from the dialog, a conversation with that project is initiated. A user may also select an existing project-level conversation. Here, the LLM agent is a RAG-based agent.

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

The system uses two stores. Neo4j holds the **knowledge graph**: documents, their internal structure, and the relationships between elements. LV items are first-class nodes carrying their structured GAEB attributes; sibling edges (`next_item`, `prev_item`) form a doubly-linked traversal of the LV in original order, and source edges link each item to its corresponding page in the LV PDF. Prose documents decompose into `SimpleChunk` and `ProseChunk` nodes; paragraph/assertion nodes and cross-document reference edges are deferred to a later sprint.

Postgres holds the **operational data**: project metadata, conversation history, token-usage and cost logs, eval records and run results, and the Prompt Library. Identity (users, roles, OAuth clients, refresh tokens) lives in a separate Postgres database owned by the `auth/` service and is never queried directly by the rest of the system — user identity flows in via OAuth2 tokens.

Elasticsearch holds the vector stores. It also stores structured LV Items and has "graph-like" attributes such as \_parent, \_sibling_previous and \_sibling_next.

## Getting Started

The system is intended to run locally via Docker Compose and is structured so that the same composition deploys cleanly to a single EC2 instance later.

Local startup, after configuring the environment file (OpenRouter API key, Postgres credentials, Elasticsearch credentials, and any other required secrets):

```
docker compose up --build -d
```

## Deployment Posture

Single-tenant. Each contracting company runs its own instance. There is no multi-tenant isolation in scope at any phase of this build.

## Companion Documents

- `docs/GLOSSARY.md` — German construction-domain terms used throughout (LV, GAEB, ZTV, OZ, Vergabe, Auftraggeber, Bauleiter, Kalkulator, Bautagebuch, and others)
- `docs/DATA_SCHEMA.md` — the canonical data model: entity names, fields, types, enums, and cross-store identity (the source of truth coding agents build against)
- `docs/DATA_ARCHITECTURE.md` — SQLAlchemy Core + Pydantic implementation guide for the Postgres data layer
