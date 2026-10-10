# Production

The production version of this application will need to include the following:

- Public Facing Free system that allows any public user to view basic information about the project as well as chat about the project using Hybrid RAG.
- Protected Admin section that allows me (the admin) to upload/ingest new documents/projects as well as to modify and change project status, visibility, etc.

# Functionality

Since the current system is a CapStone "All In One" system, some key changes will need to be made.

- Authorization: we will need a way to restrict access to the Admin API surface.
- Project Chat Prompt Engineering: we will need to change the Project Chat prompt for several objectives
  - The ability to support either English (for me and potential employers) or German (for potential clients). See "Languages" below.
  - Remove any tools that support data mutation (i.e. tools added in the Capstone that won't work for the free version)
  - Supported Tools
    - Mapping
    - Geo Search (find Asphalt Mischanlage nearest to construction site)
  - Query answering based on RAG shall include citations LIMITED in length to 3 sentences.
  - Query answering based on RAG shall include links and pointers to the original documents. Thumbnails MUST BE REMOVED.
  - Regelwerk documents MUST not include Citations, they can ONLY include the Regelwerk identifier. In place of a citation, the user must be informed that they need to get that data themselves.
  - Additional controls to make sure hackers don't jailbreak the system.
- Enforce token usage limits, monthly cap and per user caps.
- Data Masking: see "Data Masking" below. One rule, applied at ingestion and again at prompt time.
- Add Impressum und Datenschutzerklärung
- Data Mutation UI and Functionality now goes to the Admin site, perhaps I create an Admin chat agent with the mutation tools exposed to that agent. Doesn't really matter, the important thing is that those functions are protected.
- Instrumentation in Phoenix
- Replace the NER "classroom" functionality (NLP analysis modal, NER flags, LLM error analysis) with a real extraction step in the ingestion process. See "Ingest Project". Entity Rules remain, as the input to that extraction.

## Languages

- ALL PUBLIC interfaces (UI text, chat answers, legal pages, the retention notice) support multiple languages. Initial languages: English and German.
- Extracted domain values (Leistungsverzeichnis, Vorgänge, Baustoffe, Regelwerk identifiers) are NOT translated; they stay in German as in the source documents.
- Internationalisation (i18n) is a requirement from the start: all user-facing text is externalised, and adding a language must only require a new translation file, not code changes. No i18n library is chosen at this point.
- Further languages are a real possibility: India and China have a large volume of road and bridge projects, and an AI document assistant in those languages may be of value. Hindi and Chinese are candidates, not commitments.

## Data Masking

- The ingestion process shall mask the names of individuals before any chunk is stored, embedded, or sent to an LLM (unless that LLM is local). Company names are allowed and must not be masked.
- Any prompt to the LLM that contains the name of an individual, whether entered by the user OR retrieved via RAG where the ingestion masking failed, must be masked OR the prompt rejected.
  - RULE TBD: define when to mask and when to reject, and what the user sees in each case.
- The unmasked originals remain in object storage, accessible from the Admin site only.

## Retention

- Conversations: 24 hours from last activity, then deleted.
- Traces (Phoenix): 30 days.
- Expired tenders (ANGEBOT_FRIST_ABGELAUFEN): kept indefinitely; deleted manually by the admin.
- The retention periods are stated in the Datenschutzerklärung.

## Public Site

- No login. Each visitor is identified by an anonymous session ID (cookie); the IP address is a secondary key for rate limiting.
- Initial screen shows a list of projects with visibility PUBLIC. Projects whose Angebotsfrist has passed are shown with status ANGEBOT_FRIST_ABGELAUFEN.
- This is really the ONLY public functionality.

### Project Card

A project card will show details about the project, extracted from the various documents, each piece of information should provide provenance and confidence scores. Here we will also want material aggregates as well as vorgaenge listings (NLP and NER). Finally, a further detail screen for LV Items. The user will have TWO chat options, a General Chat about projects or a Chat about an LV item.

Chat data is stored server side, keyed by the anonymous session, with a per-session limit. Retention is 24 hours from last activity (see "Retention"). The retention period must be made VERY CLEAR to the user in the chat UI itself, not only in the Datenschutzerklärung.

- Store: DECISION PENDING, leaning Redis. Redis gives built-in key expiry for the 24-hour retention, so no scheduled deletion process needs babysitting, and the same store can hold the anonymous sessions and the rate-limit / cap counters. Postgres would need a recurring cleanup job.
- Abuse detection and analysis do not depend on the chat store: the usage log (per call, per session) and the Phoenix traces (30 days, prompts and answers included) are the records used for review. The chat store only serves the live conversation.

#### Project Card Details

- Name
- Link to Source tender portal
- Vergabestelle
- VergabeID
- Tender Open Date
- Bid Deadline
- Bindefrist
- Project Start
- Project End
- Description
- Aggregates (Materials and Processes)
- Identified Regelwerk (identifiers only, each with a link to the original data provider; never the norm text)
- LV Items
- Status (see "Project Status and Visibility")

Every extracted field value carries provenance (source document, page, passage) and a confidence score, as produced by the ingestion extraction step.

#### Project Status and Visibility

- Status is derived from the dates, not set by hand:
  - ANGEBOT_OFFEN: today is before the Bid Deadline.
  - ANGEBOT_FRIST_ABGELAUFEN: the Bid Deadline has passed. This is the final status; contract awards are mostly not published, so there is no awarded state.
- Visibility is set by the admin:
  - DRAFT: ingested, visible in the Admin site only.
  - PUBLIC: shown on the public site.
  - HIDDEN: removed from the public site (e.g. after a data removal request), kept in the Admin site.

#### LV Items

- The way it looks now but NO NLP analysis, just a "Chat" button.

### Data Removal Request

Provide a way for a third party (Vergabestelle, or Ingenieurbüro) to request that information be removed from the site.

## Admin Site

### Ingest Project

Basically what we already have but enhanced with better ZIP preprocessing as well as data masking (see "Data Masking"). Norm documentation must be excluded... even if reprinted in the tender documents; only the Regelwerk identifiers are kept.

#### Extraction (replaces the NER classroom)

The ingestion process extracts, per project, with provenance (document, page, passage) and a confidence score on every value:

- The Project Card fields (dates, Vergabestelle, VergabeID, description, ...).
- Material aggregates and Vorgänge listings (NER via Entity Rules, plus LLM where the rules are not enough).
- The identified Regelwerk identifiers.

Values the admin corrects by hand keep their provenance as "admin".

### Manage Projects

Same as what we have now, plus setting visibility (DRAFT / PUBLIC / HIDDEN) and correcting extracted field values.

### Katalog Management

Same.

### Entity Rule Management

Needs another look but for now let's call it SAME. The rules feed the extraction step above.

### Prompt Management

A way to modify prompt information (providers, prompts, endpoints and spend limits). We already have most of it but it should be double checked.

- API Keys are never stored in the database and never shown in the UI.
  - A provider / endpoint record stores a key reference (the name of a secret), not the key value. The server resolves the reference from deployment secrets at runtime.
  - The admin can switch an endpoint between key references in the management UI without ever seeing a value.
  - Rotating a key is a secrets change plus a restart or reload; the endpoint record does not change.
  - Future SaaS case: customer-supplied keys become a second reference type backed by encrypted storage; the endpoint record and the resolution step stay the same.

# Operational

- New routine for Zip Ingestion: this is partially also functional in that I will want to support new chunking (i.e. extracting info from Querschnitt diagrams). But most important is that the routine ingests as much data as it can to be credible without causing the errors it encounters now.
- Schema Migrations: add the ability to migrate schema changes to live databases. i.e. Alembic.
- Deployment Hardening: modify docker-compose.yml to close off internal ports, making sure that only 80/443 ports are open.... I'd also want to make sure there is something like www.strassenbau-vergabe-assistant and admin.strassenbau-vergabe-assistant. This needs to be built in a way that I can simply run docker compose on an AWS instance or a GCP instance or an Azure Instance and all the necessary services, databases, etc. start up and run without any security weaknesses (errant open ports, etc.). We could also assume that an ALB and firewall are in front of the instance as well.
- Make sure Phoenix management is secured from public accessibility.
- TODO: define a backup and recovery plan (Postgres, object storage, Elasticsearch index or its rebuild), including a restore test.
- TODO: define monitoring requirements (service health, ingestion job status, spend vs. cap, error rates).
- TODO: define alert requirements (service down, spend cap approaching / reached, ingestion failures, abuse patterns).
- TODO: define build requirements (reproducible images, pinned versions, build pipeline, how a release reaches the instance).
