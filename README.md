# Roadbuilders Assistant

A domain-focused RAG system that helps cost calculators (Kalkulatoren) at road construction contracting companies work through public-tender (Vergabe) documents and prepare bids. The system ingests the full document set for a tender, builds a structured knowledge representation, and answers grounded, citation-backed questions about it.

This README explains what the system is and what it does. Architecture decisions and code-level guidance live in `ARCHITECTURE.md` and `CLAUDE.local.md`. German construction-domain terms used throughout are defined in `GLOSSARY.md`.

## The Problem

A typical road construction tender (Straßenbau-Vergabe) ships as a stack of long, interrelated documents: a Baubeschreibung describing the work, a Leistungsverzeichnis (LV) with hundreds of priced line items, Vertragsbedingungen and Besondere Vertragsbedingungen, Zusätzliche Technische Vertragsbedingungen (ZTV), a Baugrundgutachten, sometimes Baupläne and Karten, plus a list of Vorzulegende Unterlagen the bidder must supply.

A Kalkulator reading this stack has to:

- Decide whether the project is even viable for the company to bid on
- Surface missing information and resolve conflicts between documents
- Assemble cost factors from internal data and subcontractor offers
- Produce a transparent bid that holds up to scrutiny in standard cost-structure review

The documents are long, redundant, and densely cross-referenced. Specifications in the ZTV qualify items in the LV; the Baubeschreibung sets expectations that constrain how individual Positionen are priced; missing details in one document often surface as fatal gaps only after another document is read. Doing this by hand for fifteen tenders in a pipeline is the daily reality, and most of the cognitive load is retrieval, not judgment.

Roadbuilders Assistant exists to take the retrieval load off and let the Kalkulator spend their time on judgment.

## Who Uses It

Three user groups, each with a defined permission scope. Permissions are role-based and project-scoped: once a project is ingested, every authorised user of every role can access it. Fine-grained per-user permissioning is a Capstone concern, not a current one.

**Administrator** — manages users, manages projects (create, configure, archive), and ingests data of any type. Effectively a superuser.

**Kalkulator** — creates projects, adds individual documents to existing projects, and queries the system through chat. This is the primary user role.

**Bauleiter** — same as Kalkulator, plus an `ingest_reports` capability for uploading site reports, Bautagebücher, and similar field documents. The Bauleiter role becomes more relevant in later phases when the system supports construction-phase reference.

## What It Does

The system has 2 distinct functional surfaces, and 2 auxiliary surfaces, all driven by a front-end UI chat dispatcher interface.

### 1. Project Ingestion

A project corresponds to one tender. Creating a project means establishing a per-project knowledge base into which the tender documents are ingested. The system ingests two categories of input:

- **Prose documents** (All Documents) — all documents will be ingested with a simple chunking system into a SimpleChunk structure in the vector store.
- **Leistungsverzeichnis** - LV documents will have a special parsing step that extracts LV Items into structured storage (db) and then SimpleChunks will be generated on those LV Items.

This approach allows us to run a "simple" retreival and an "plus" retrieval. As more document parsers are created, the "plus" gets better and better. But for now, we stick with just LV.

### 2. Project Chat

This is a chat system driven by RAG retrieval. The retrieval system has options that can be set in the UI. These options include:

- Query Techniques: Single or Multi
- Retrieval Method: Simple or Plus (LV Special)
- Options: BM25, Cross-Encoder

The user chats with the system and it uses RAG to answer the questions where appropriate. A simple gate is if there is a question about a SPECIFIC OZ in the project. There we should provide an LVItem lookup tool (by project_uuid and OZ). Another gate would be, "Show me the LV Items for {Section}", which would be a listing of OZ for a given parent OZ. But those are the only gates besides saying "I can't help you" if the question is completely irrelevant. This gating should be an LLM prompt called "ClassifyProjectChatUserMessage". Possible outputs would be:

- tool_call: LV_Item_Lookup
- tool_call: List_LV_Items_by_Parent_OZ
- tool_call: RAG_Context_Retreival (with UI-defined options)
- "I can't help you, sorry."

### 3. Project Management - React UI Component ModalDialog Overlay

This is a React UI Component (overlayed as ModalDialog) that allows the user to manage projects. This includes viewing a list of project cards, modifying projects, creating projects, viewing documents in projects, adding/removing documents in projects. There should be the ability to launch a chat from a specific project.

### 4. Prompt Management - React UI Component ModalDialog Overlay

Every LLM call in the system is dispatched through the **Prompt Library**: a versioned store of system prompts, each pinned to a specific model, temperature, sampling settings, and (where structured output is required) a response schema. Editing a prompt creates a new immutable version; call sites stay on whichever version they reference until explicitly migrated, so a prompt change cannot silently destabilise an upstream pipeline. A small UI surfaces the prompts and their version timelines, and lets authorised users read, edit, and version AND test the prompts.

---

### **_Dispatcher/Tools_**

The default UI chat modality. This chat interface tries to determine what the user wants to do:

- Project Chat: the user wants to talk about a project, brings up the Project Interface so the user can choose a Project to talk about.
- Prompt Management: the user wants to manage prompts, brings up the Prompt Management interface.
- New Project Ingestion: brings up the Add Project interface, which is in and of itself a part of the entire Project Management system.

## Knowledge Representation, at a Glance

See DATA_SCHEMA.md.

## Getting Started

The system is intended to run locally via Docker Compose and is structured so that the same composition deploys cleanly to a single EC2 instance later.

Local startup, after configuring the environment file (OpenRouter API key, Postgres credentials, Elasticsearch credentials, and any other required secrets):

```
docker compose up --build -d
```

## Deployment Posture

Single-tenant. Each contracting company runs its own instance. There is no multi-tenant isolation in scope at any phase of this build.

## Companion Documents

- `GLOSSARY.md` — German construction-domain terms used throughout (LV, GAEB, ZTV, OZ, Vergabe, Auftraggeber, Bauleiter, Kalkulator, Bautagebuch, and others)
- `DATA_SCHEMA.md` — the canonical data model: entity names, fields, types, enums, and cross-store identity (the source of truth coding agents build against)
- `DATA_ARCHITECTURE.md` — SQLAlchemy Core + Pydantic implementation guide for the Postgres data layer
- `INGESTION.md` - details about the INGESTION process.
- `RETRIEVAL.md` - details about the RETRIEVAL process (surfaced in Project Chat).
- `LV_PARSE.md` - companion to INGESTION.md.
