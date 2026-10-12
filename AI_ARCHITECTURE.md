# AI Architecture

How the system uses LLMs: the ingestion and retrieval pipelines, the two stateful agents (Project
Chat and the EKT Calculation Agent), the Katalog Chat agent that maintains the reference data, and
the prompt/model infrastructure underneath them.

The governing design rule: **the LLM judges, deterministic code computes.** LLMs classify
positions, segment and extract text, and decide which tool to call; every euro and every quantity
is produced by `Decimal` arithmetic over cataloged formulas, and every resolved value carries
provenance (source, confidence, evidence). System processes, stores, and the data model are in
`APPLICATION_ARCHITECTURE.md`; domain terms in `GLOSSARY.md`.

## Ingestion Pipeline

Ingestion runs in the worker (job mechanics in `APPLICATION_ARCHITECTURE.md`). The document type
is decided at upload, server-side, in `shared/services/ingestion/classify.py`, and the worker
dispatches on it: LV (GAEB), FORM (fillable PDF form) or PROSE (every other PDF). Whether a
document is ingested at all is a separate rule in `ingestion/enqueue_policy.py` (a Bieter form
starts `skipped`).

```mermaid
flowchart TD
    PDF["PDF upload (prose)"] --> EX["extract text lines<br/>(poppler pdftotext -bbox-layout)"]
    EX --> SL[("source_lines — Postgres<br/>canonical per-line text")]
    PDF --> TH["render page thumbnails → MinIO"]
    SL --> SPL["text splitter"]
    SPL -->|"source_doc_type = DOCUMENT"| SC[("SimpleChunk index — Elasticsearch<br/>embedding + BM25")]
    FORM["PDF upload (XFA / AcroForm / flattened form)"] --> FX["form extractor<br/>(XFA packets / toggles by geometry)"]
    FORM --> TH
    FX --> SL
    FX --> FF[("form_fields — Postgres")]
    SL --> FSPL["one chunk per form section<br/>(checked options only)"]
    FSPL -->|"source_doc_type = FORM"| SC
    GAEB["GAEB upload (.d83 / .x83)"] --> GP["deterministic GAEB parse<br/>(no LLM)"]
    GP --> LVI[("lv_items — Postgres")]
    GP --> LVT[("lv_texts — Postgres")]
    LVI -->|"chunk langtext_resolved, source_doc_type = LV_ITEM"| SC
    LVT -->|"chunk heading + body, source_doc_type = LV_TEXT"| SC
```

- **Every prose PDF** gets the common stage: per-line text extraction into `source_lines` (the
  canonical text — the search index is fully rebuildable from it), page thumbnails to MinIO, and
  simple chunking into embedded `DOCUMENT` chunks. This includes the LV print-layout PDF, which is
  treated as prose. Poppler renders static text and the appearance streams of filled AcroForm
  text fields with their geometry; it does not render checkbox or radio state in a usable form,
  and it does not render dynamic XFA forms at all (those yield Adobe's "Please wait..." page).
- **Forms (Formblätter)** come in three kinds and are detected from the bytes, not the name: a
  PDF with an XFA packet, an AcroForm with at least 3 fillable (non-pushbutton) fields, or a
  **flattened** form (zero fields, the boxes drawn as vector squares and the ticks as text
  glyphs) whose printed footer or filename token names a Formblatt of the role table. An
  `/AcroForm` dictionary alone is not enough — plans, Gutachten and the LV print PDF carry one
  with zero fields and stay prose, as does a zero-field PDF without an id. The Formblatt id comes
  from the page footer first (`NNN HVA B-StB <Titel> MM-YY`, `forms/identify.py`; VHB and WSV
  forms print no usable number), then from the filename token (`FB 312-B`, `HVA_B_StB_121`,
  `VHB_221`, `EFB-Preis`); the role is looked up per family in a code table (`forms/role.py`),
  then from Bieter title keywords, else `unbekannt`. **Identified Bieter forms are stored but not
  ingested** (job `skipped`; "Trotzdem indexieren" requeues it); a keyword-only Bieter form,
  Vergabestelle and unknown forms are extracted in one pass into `source_lines` and structured
  `form_fields`, on one line contract for every kind: `## <section>` headings, `label: value`
  for filled fields, `[x] <text>` / `[ ] <text>` for options, static prose untouched. XFA is read
  from the embedded `template` + `datasets` XML (static `<draw>` text as lines, a `checkButton`
  as an option line, a radio group as `caption: <selected>`; scripts are not evaluated, so
  script-hidden fields are emitted anyway, and XFA lines carry no geometry). AcroForm and
  flattened forms keep the poppler page text and attach each toggle by geometry
  (`forms/toggles.py`): the kind-specific reader only locates `Toggle`s (widget `/Rect` plus
  `/AS` state; or a 6–12pt vector square with a tick glyph centred inside it), and one shared
  step re-attaches the tick glyphs and section numbers that `pdftotext -bbox-layout` emits as
  blocks of their own, prefixes the state onto the printed line to the right of the box (the
  `/TU` tooltip is the fallback when no printed line is there; a box with neither is counted as
  unresolved and logged), and opens a section at every numbered heading at the left margin
  (`## Seite n` for a page without one). Forms are never read by a VLM or OCR. `chunk_form` then
  emits one `FORM` chunk per section holding **only what is checked**: an unchecked option is
  dropped together with every line printed under it (anything indented past the option's number
  column until the next heading or a line further left), a checked option loses its marker, and
  a section left empty by that gets the single line `keine Option angekreuzt`, so "nicht
  angegeben" stays distinguishable from "Abschnitt fehlt". Unchecked options remain in
  `source_lines` and `form_fields` (value `nein`) and on the thumbnail. A line is never split; an
  over-long section continues under its heading. Forms skip the LangChain pass. Thumbnails are
  still rendered (for XFA they show the placeholder page, so the document dialog opens on the
  Felder tab).
  Known limitations: XFA lines have no geometry, so nothing can be highlighted on an XFA
  thumbnail and nesting under an unchecked option is not applied there (only the line itself is
  dropped); VHB and WSV forms get no footer id, so their `form_id` depends on the filename;
  keyword-only forms (no footer, no token) and scanned forms without a text layer stay prose;
  hand-drawn ticks and filled squares without a glyph read as unchecked (the unresolved/checked
  counts in the activity log are the signal); `unbekannt` forms are indexed without a role
  filter; a PDF bundling several Formblätter takes the role of its first token.
- **LV items come exclusively from GAEB files.** A `.d83` (fixed-format CP850 records) or `.x83`
  (GAEB DA XML) upload is an LV document by definition and parses deterministically —
  no LLM. Every Hinweistext (D83 record `20`, X83 `Remark`) becomes a `Remark` node that records
  only what the file states with certainty: its structural parent (LV root or LV-Gruppe) and its
  sequence within that parent. A position's `hinweis` is the positional projection of those nodes
  — every Hinweis in the enclosing containers that precedes it, outermost first — plus any
  Ausführungsbeschreibung (X83 `PerfDescr`) the item references. LV-level free text outside the
  hierarchy (D83 `T0`..`T9` vertragliche Regelungen, X83 `AddText` before/after the `BoQ`) is kept
  apart as `AddTextBlock`s (Vortext/Nachtext). Both the blocks and every Remark node persist as
  `lv_texts` rows (replaced wholesale on re-ingest) and are served on the project's LV-Texte tab.
  The parse also resolves "wie in voriger Position" back-references into `langtext_resolved` and
  links the OZ hierarchy (`level`, `parent_oz`, `prev_oz`/`next_oz`). Items are chunked into
  `LV_ITEM` chunks from `langtext_resolved || langtext`, carrying denormalized `oz` and `stl_nr`;
  LV texts are chunked into `LV_TEXT` chunks (heading + body, `oz` = the Hinweis's LV-Gruppe).
- **A project can hold several LV documents**, one per GAEB file (e.g. the same LV as X83 and
  D83, or one LV per Los). Uploading a GAEB file adds a new LV document next to the existing ones;
  each keeps its own `lv_items`, `lv_texts` and chunks, all keyed by `document_uuid`, and deleting
  one LV document leaves the others intact. Re-ingestion in general archives a source's prior
  chunks to the `_archive` index with an `archived_at` stamp instead of overwriting; Postgres rows
  upsert on natural keys.
- An earlier LLM-based parse of LV **PDFs** (segmentation by line spans, verbatim slicing by code)
  is retired from the pipeline; it survives as a standalone harness
  (`python -m scripts.run_lv_extraction`) for experimentation.

A second, LangChain-managed index (`idx-langchain-roadbuilders`) is populated in parallel for
prose PDFs and serves as an alternative chunking/embedding path inspectable per document in the
UI.

## Retrieval

Retrieval is always project-scoped and configured per turn from the UI (modality, multi-query,
BM25, rerank). Pool sizes come from settings: 5 query variants, ~50-candidate pool, top 10 final.

```mermaid
flowchart TD
    Q["query + per-turn config"] --> MQ{"multi-query?"}
    MQ -->|"yes"| VAR["LLM: 5 query variants"]
    MQ -->|"no"| SCOPE
    VAR --> SCOPE["project filter + modality scope"]
    SCOPE --> D["dense kNN per query"]
    SCOPE --> L["BM25 per query (optional)"]
    D --> RRF["Reciprocal Rank Fusion<br/>(no-op for a single list)"]
    L --> RRF
    RRF --> POOL["candidate pool (~50)"]
    POOL --> CE{"cross-encoder?"}
    CE -->|"yes"| RER["multilingual rerank"]
    CE -->|"no"| K
    RER --> K["top-10 context, numbered sources"]
```

- **Simple modality** searches `DOCUMENT` and `FORM` chunks — every document's prose chunks,
  including the LV PDF's own, and the extracted forms. A `FORM` chunk is cited by page like a
  `DOCUMENT` chunk.
- **Plus modality** represents the LV structurally: the `LV_ITEM` and `LV_TEXT` chunks of every
  LV document of the project (positions plus each LV's Vorbemerkungen/Hinweise) plus all
  `DOCUMENT` and `FORM` chunks. GAEB LV documents produce no `DOCUMENT` chunks, so LV content is not counted
  twice. The filter needs no document lookup and works the same for zero, one or several LV
  documents; with none, Plus returns what Simple would.
- RRF fires whenever more than one ranked list exists (multi-query or BM25); the cross-encoder is
  the only post-retrieval stage. HyDE was evaluated and rejected: for legally binding tender text,
  hypothetical documents pull semantically-similar-but-irrelevant material into the context.

## Project info extraction

A project created from a tender ZIP starts with only a placeholder name. Once its documents are
ingested, the worker fills the header fields (Projektname, Maßnahmenummer, Vergabenummer,
Vergabestelle, Bauleistung, Baustelle, Projektbeschreibung) from them in one project-level job.

```mermaid
stateDiagram-v2
    [*] --> Queued: POST /projects/from-zip<br/>(or "Projektinfo neu ermitteln")
    Queued --> Queued: project has queued/running ingest jobs
    Queued --> Running: all ingest jobs done or failed<br/>→ worker claims the job
    Running --> Running: per query: retrieve (PLUS) → synthesize
    Running --> Done: found values written to projects columns
    Running --> Failed: error (retried while attempts remain)
    Done --> [*]
    Failed --> [*]
```

- **Completion is a claim rule.** The `project_info_jobs` row is enqueued with the documents, but
  `claim_next` only picks it once no ingest job of the project is queued or running. A failed
  ingest job does not block, so a project with one broken document still gets its info.
- **Two texts per query.** Each `ProjectInfoQuery` key has an append-only, editable
  `rag_query_versions` row in the job's language (`PROJECT_INFO_LANGUAGE`). Its `query_text` is the
  retrieval question (embedded and BM25-matched, PLUS modality, multi-query, cross-encoder); its
  `answer_instruction` goes only to the synthesis LLM and sets the value format.
- **No free text in a column.** One structured `PROJECT_INFO_RESOLVE` call per query returns
  `{reasoning, gefunden, wert, konfidenz, beleg}` from the retrieved snippets alone, the same
  shape as the project-context resolver. Only `wert` with `gefunden=true` is written, to the
  query's fixed column; a miss leaves the column untouched. A ZIP-created job overwrites (the only
  value present is the placeholder name); a manual re-run asks for confirmation before it does.
- Every query's outcome, including the evidence quote and query version, is stored on the job row
  and shown per field on the project page. `location` is stored as text; geocoding stays with the
  project-context resolver.
- **Activity log.** Each step writes a line to `project_info_activity_log`, tagged with a
  `ProjectInfoPhase`: `claim` (attempt, language, overwrite flag, how many query versions were
  found), `retrieve` ("retrieving <key> (v<version>)", chunks after rerank, or "skip: no query
  version"), `synthesize` (the LLM's `gefunden`, `konfidenz` and the start of `wert`) and `write`
  (the columns written, or skips for columns already set, and the closing "done in x s, n of m
  found"). Mock mode writes the same lines marked "(mock)". The lines are buffered and flushed
  like the ingestion activity stream, and each flush also refreshes the job's lease. The ingest
  console shows each job's latest line and streams the full log in its activity terminal.

## Project Chat Agent

Persistent, project-scoped conversations. One turn = `POST /conversations/{id}/turn`, streamed
back as SSE.

```mermaid
stateDiagram-v2
    [*] --> Guard : POST …/turn
    Guard --> PersistUser : input guard passed
    PersistUser --> RebuildHistory : user + assistant rows only
    RebuildHistory --> Assistant
    Assistant --> Tool : tool call → function_call
    Tool --> Assistant : result → function_call_output
    Assistant --> Finalize : final answer (text_delta stream)
    Finalize --> [*] : done
    Finalize --> Calculator : calculate_ekt signaled (position chat)
    Calculator --> [*] : calc_start … Gate-1 interrupt, same stream
```

The turn pipeline: boundary input guard → persist the user message → rebuild history (only user
and assistant rows are replayed; tool traffic is persisted for display but re-derived fresh each
turn) → a LangChain `create_agent` ReAct loop over a streaming OpenRouter model → persist the
assistant text. Tool calls and results stream as typed SSE events and persist as
`function_call` / `function_call_output` message rows the UI renders (LV tables, citation panels,
maps).

The tool set:

| Tool | Does |
| --- | --- |
| `get_project_context` | Semantic RAG over all project documents; returns numbered evidence. |
| `get_lv_context` | Semantic RAG restricted to LV positions. |
| `get_lv_all` | Every LV position (OZ, Kurztext, Menge, Einheit). |
| `get_lv_single_item` | One position by exact OZ. |
| `get_lv_group_items` | All positions under a section OZ. |
| `aggregate_lv_items` | Quantity aggregation over a free-text predicate: an LLM judges which positions match, Python sums the Mengen (grouped by Einheit; Bedarfs-/Eventualpositionen split out). |
| `render_map` | Geocode an address, render a static map PNG to storage, display inline. |
| `calculate_ekt` | Position chat only: a pure control signal that hands the stream to the calculator. Not persisted, not rendered. |

Citations: retrieval tools feed the model a numbered evidence block and the model grounds its
answer with `[n]` markers. The agent offsets source numbers across multiple retrieval calls within
a turn so `[n]` stays unique; the full retrieval trace (including thumbnails) rides the tool-result
event for the UI's citation panel.

**Position chat** is the same agent bound to one LV position (its Kurztext/Langtext/Menge as
permanent context). When the Kalkulator asks for a calculation, the agent emits `calculate_ekt`;
the router swallows the signal and chains `CalculatorRunService.start` into the same SSE response —
text, `calc_start`, calculator reasoning, and the first interrupt arrive as one stream.

**The Dispatcher** is the same machinery minus state: a single-shot command-bar loop (no history,
nothing persisted, capped at 8 tool turns) whose tools open UI views — projects, prompts, execution
log, usage log, ingest console.

## EKT Calculation Agent

Turns one LV position into an auditable EKT. Output: an **EKT row** (Einheits- and Gesamtpreis
with a cost line per Vorgang and Kostenart), the **Nachweistabelle** (every variable touched —
value, unit, source, evidence, and for formulas the expression and its inputs: the full derivation
tree), and a short narration. Rendering the result as a VHB Formblatt 223 row is a planned
enhancement — the cost lines keep the engine's six Kostenarten today.

### The engine underneath

The deterministic `kalkulation_v2` engine owns a four-level catalog spine — **Leistung** (the
what; a leaf) fulfilled by a selected **Bauverfahren** (the recipe: ordered **Vorgänge**, each
binding an **Ausführungsart** equipment slot) — plus the variable layer: each Vorgang carries a
**Rechnung** that *instantiates* ~16 parameterized base formulas (binding their parameters to
`kontext`/`stammdaten`/`baustoff`/sibling-instance sources), and those bound variables resolve
through per-variable cascades (Langtext → RAG → HITL → Stammdaten → Konstante). The resolver checks
already-supplied values first — that is the seam: the graph fills judgment values
(`LANGTEXT`/`RAG`/`HITL`) into the context, and the engine computes the rest (`STAMMDATEN`/`KONSTANTE`,
and the Rechnung's formula instances) as pure
`Decimal` functions with cycle detection. All catalog content lives in the DB-backed Katalog
(loaded at startup, reloaded on activation); adding a Leistung or recipe is catalog data entry —
the graph topology never changes.

### The graph and its four gates

A LangGraph state machine, checkpointed per conversation (`AsyncPostgresSaver` keyed by the
conversation UUID), so every gate pause survives across HTTP requests. Human decisions are real
`interrupt()`s resumed with `Command(resume=…)`; the UI renders each gate as a structured form,
not free text.

```mermaid
stateDiagram-v2
    [*] --> launch
    launch --> extract_chat_values : harvest values stated in chat (source 0)
    extract_chat_values --> load_project_context : load + RAG-resolve globals, reconcile vs chat
    load_project_context --> project_context_review
    project_context_review --> project_context_review : Gate 1 loop — required global missing (Baustelle not geocoded)
    project_context_review --> classify_leistung : Gate 1 confirmed
    classify_leistung --> leistung_bv_review : LLM proposes Leistung
    leistung_bv_review --> resolve_material : Gate 2 — Leistung confirmed, Bauverfahren picked
    resolve_material --> material_review : recipe consumes a Baustoff (BM25 proposal)
    resolve_material --> rank_lieferanten : material-free recipe (Gate 3 skipped)
    material_review --> rank_lieferanten : Gate 3 — Baustoff confirmed
    rank_lieferanten --> bind_resources : suppliers ranked by delivered price
    bind_resources --> bind_lieferant : machines right-sized per slot
    bind_lieferant --> derive_required_variables : supplier price + haul distance bound
    derive_required_variables --> resolve_variables : walk recipe Rechnung bindings to all leaves
    resolve_variables --> variable_review : propose value + provenance + tier per leaf
    variable_review --> compute : Gate 4 — full set confirmed
    compute --> render_output : deterministic engine run
    render_output --> [*] : EKT row + Nachweistabelle + narration
    project_context_review --> [*] : cancel
    leistung_bv_review --> [*] : cancel
    material_review --> [*] : cancel
```

- **Gate 1 — project context.** Project-scoped globals (Baustelle, Deponie, strip dimensions,
  Fräsgut class) are loaded from their SCD-2 store, RAG-resolved where unset, and reconciled
  against values stated in chat (confirm / override / conflict per variable). Required globals are
  enforced: the gate loops until the Baustelle geocodes or the user cancels. Confirmed overrides
  persist as new context versions — the next position in the project inherits them.
- **Gate 2 — method.** The classification LLM proposes the Leistung; the Kalkulator confirms or
  corrects it and picks the Bauverfahren from the mapping's ordered candidates. This precedes
  variable work because the worklist is derived from the chosen recipe.
- **Gate 3 — material.** For recipes that consume a graded Baustoff, a BM25 matcher grounds the
  Langtext's norm designation to a catalog code — it can only return cataloged codes. High-scoring
  matches auto-apply; otherwise the top hit and alternates are surfaced for confirmation.
  Material-free recipes skip this gate.
- **Gate 4 — variables.** Every resolution leaf the recipe's Rechnung binds is proposed with value,
  provenance, and confidence: extracted inputs (chat/Langtext/RAG/default), rates, and master
  data. The review is tiered — low-confidence and high-stakes variables are surfaced for explicit
  decision; confident extractions, rates, and Stammdaten are pre-accepted in a collapsed tier,
  still overridable. The same form carries machine-per-slot and supplier overrides. Submit
  confirms the full set; overrides are captured to the corrections log and can be marked as
  ground truth (see `AI_EVALUATION.md`).

### Resolution precedence

Per variable: (0) values the Kalkulator already stated in chat are harvested up front and pinned —
no search runs for them; (1) Langtext extraction; (2) RAG over the project corpus (Plus modality,
multi-query, BM25, rerank); (3) a flagged Konstante default where the catalog defines one. The
extraction LLM copies values verbatim with an evidence quote — it never computes. A value that
cannot be found surfaces at Gate 4 as an open decision, never a silent guess.

### Resource binding

- **Machines** — candidates come from the Katalog fleet by Ausführungsart; the default is
  right-sized: the smallest machine that clears the job within the configured target hours. A
  bound machine's rates and per-Betriebsart productivity feed the Maschine cost lines and the
  `arbeitszeit` instance (the labour-hours basis) and stay overridable at Gate 4.
- **Suppliers** — after material confirmation, Lieferanten with a valid ex-works price and known
  coordinates are pre-filtered by great-circle radius (default 100 km), route distances to the
  Baustelle are computed in one route-matrix call, corrected by an HGV detour factor, and offers
  are ranked by delivered price (Werkspreis + €/t·km transport). The chosen supplier's price
  overrides the material's base price through the standard master-data bridge, and the haul
  distance feeds the Antransport (F_TRANSPORT) instances. Switching supplier at Gate 4 re-applies
  from the ranked list without re-routing.

## Katalog Chat Agent

The maintenance agent for the reference data. Same ReAct/streaming machinery as project chat, with
a seeded, versioned system prompt (the Katalog-Handbuch) and three tool families: **34 read tools**
(browse/search every entity, base-formula explanation with LaTeX + declared parameters, the
`ontologie_lookup` "where does this input live" tool, where-used impact analysis, SCD-2 history,
price validity), **17 write tools** (draft new/changed base Formeln, Variablen, Baustoffe,
Lieferanten, Preise, Maschinen, taxonomy entries, Leistung–Bauverfahren mappings), and the
**recipe compiler** (W18), which drafts one coherent bundle spanning any subset of entities.

```mermaid
stateDiagram-v2
    [*] --> Turn : user message
    Turn --> Read : read tools (T1–T34)
    Read --> Turn : catalog facts
    Turn --> Write : write tool (W1–W17, W18)
    Write --> Validate : write facade — validate bundle
    Validate --> Turn : invalid — errors returned, nothing saved
    Validate --> Draft : valid — rows saved as entwurf under one bundle_uuid
    Draft --> Card : confirm card rendered from the tool result
    Card --> Activated : human clicks Aktivieren — re-validate, atomic swap, Stand+1, engine reload
    Card --> Discarded : human clicks Verwerfen
    Activated --> [*]
    Discarded --> [*]
```

The human-in-the-loop boundary is structural, not prompt-based: write tools go through a facade
that exposes validate, save-draft, and discard — activation is deliberately absent from the
agent's reach and exists only as an API endpoint behind the authenticated routes. Validation is a
pure rule set over the draft plus the active catalog: a base formula must parse, close over its
declared parameter signature, and carry mandatory prose (on the formula and each parameter); every
Vorgang Rechnung must be evaluable — its instances bind known, producible variables with
**dimension-compatible units** (a scalable cm→m is fine; a dimension change is a Mengengerüst
formula's job, not a binding); a candidate formula **structurally isomorphic** to an existing base
formula is rejected ("instantiate, don't mint"); every variable carries prose; every code reference
resolves; prices name known parties with ordered validity; same-key rows are reported as updates.
Activation re-validates against the *current* catalog, activates atomically, closes superseded
price validity windows, bumps the global Stand, and reloads the running engine.

Guard rules from the Handbuch (the load-bearing ones): never invent codes — search first (the
`ontologie_lookup` tool answers "where does this input live"), answer only from tool results; never
self-activate; never invent a DSL function — a missing function is an engineering request, not a
formula; **instantiate base formulas, don't mint** — a new base formula only for a genuinely new
shape; rates belong in Stammdaten variables; the Leistung's unit fixes the booked geometry the
Rechnung binds against.

The recipe compiler composes with the same flow: it looks up the ontology, normalizes a whole-recipe
bundle of base-formula instantiations, runs the full rule set (incl. structural dedup + unit
compatibility), enforces a coverage contract (every code defined or referenced must be justified as
either reuse or new), and adds non-blocking warnings — BM25 duplicate probes and geometry-dependency
checks — before saving one draft bundle for the same confirm card.

## Prompt Management

Every persistent prompt is an immutable `PromptVersion` row pinning system text, model, and
sampling parameters per `prompt_type`; creating a new version never disturbs the old, and call
sites load the latest at runtime. Prompts are seeded from `.prompt` files (YAML frontmatter +
system text) — currently twelve types: `project_chat`, `dispatcher`, `conversation_name`,
`aggregate_lv_membership`, `multi_question_generator`, `project_context_resolve`, `katalog_handbuch`
(the Katalog-Chat system prompt), the calculator's four (`ekt_leistung_classify`, `ekt_chat_values`,
`ekt_langtext_extract`, `ekt_output_narrate`), and `lv_extraction` (the retired PDF-parse harness).
Seeding appends a new version per run by design — edit the file, re-seed, and the new version is live.

Structured outputs are schema-in-code: a registry maps a `prompt_type` to a Pydantic model, and
the LLM client validates every response at the boundary, so malformed output raises instead of
propagating. Adding a prompt type touches the backend enum (single source of truth), a seed file,
the load site, and the CHECK constraints that mirror the enum in `prompt_versions` and
`conversations`.

The calculator takes its model from settings rather than a prompt row (`CALCULATOR_MODEL`, plus
reasoning effort and a full mock mode for offline runs). The Katalog chat, by contrast, now loads
its system prompt AND model from the seeded `katalog_handbuch` version (the frontmatter owns the
model choice), so editing that prompt in the editor changes both — and the recipe-compiler eval
measures the live version.

## Document Reflow and NLP Analysis

The NLP analysis modal turns a Baubeschreibung's raw `source_lines` into linguistically usable text
and lets you inspect every intermediate step: reflowed blocks vs original lines, sentence
segmentation with displacy renders, POS distribution, and a domain-aware named-entity view. Its
source is fixed at open — there is no in-modal picker or free-text input: it launches either from an
ingested Baubeschreibung's "NLP-Analyse" action in the Project Documents tab (a document source) or
from an LV item's "NLP-Analyse" action (that item's Langtext + Hinweis as ad-hoc text).

`source_lines` are visual layout lines (`pdftotext -bbox-layout`), not linguistic units: German
justification hyphenates words across lines, letterheads repeat on every page, sentences span
pages, and tables shred into cell fragments. The reflow pipeline fixes this with a hybrid of the
existing poppler extraction (authoritative *text*, including filled AcroForm text fields) and the Docling layout model
(*structure*), validated in the layout spike (`nlp-playground/layout-spike/`):

```mermaid
flowchart TD
    PDF[(MinIO raw PDF)] -->|pdf bytes, rendered internally| DOCLING[Docling layout model]
    DOCLING -->|label + bbox per region| REGCACHE[(document_layout_regions)]
    DB[(source_lines)] --> JOIN
    REGCACHE --> JOIN{{bbox join: line center in region}}
    DB --> HEUR[repetition heuristic]
    HEUR --> FURN[furniture = heuristic UNION model]
    JOIN --> FURN
    FURN --> BLOCKS[typed blocks: PROSE / HEADING / LIST_ITEM / TABLE / CAPTION / FOOTNOTE]
    BLOCKS --> REFLOW[dehyphenate, join lines, merge cross-page]
    REFLOW -->|include-list filter| SPACY[spaCy de_core_news_lg + entity_ruler]
    RULES[(entity_rules table)] -->|enabled rules, only when dirty| ENSURE{{ensure_ruler_current}}
    ADMIN[Entity Rules admin page] -->|CRUD, spaCy-validated writes| RULES
    RULES -.->|mark_dirty on write| ENSURE
    ENSURE -->|rebuild ruler pipe| SPACY
    SPACY --> OUT[sentences + POS stats + entities + displacy renders]
```

Key decisions (full rationale in `openspec/changes/nlp-analysis-modal/design.md`):

- **Furniture is the union** of a repetition heuristic (digit-run-normalized text + y-bucket on
  ≥50% of pages) and Docling `page_header`/`page_footer` regions — the spike showed the heuristic
  wins on repeated letterheads, the model wins on roman-numeral front matter.
- **German dehyphenation**: a line-end hyphen joins the next line dropping the hyphen when it
  starts lowercase (`gekom-`/`menen`), keeping it when uppercase (`SRT-`/`Pendel`). Cross-page
  merges require no lowercase test — German capitalizes nouns mid-sentence.
- **Block-type inclusion is per-request config** (`include_blocks`, default PROSE + HEADING +
  LIST_ITEM); tables are excluded by default so cell fragments never reach the sentence splitter,
  but can be toggled on in the modal to observe the degradation.
- **Models load lazily** (spaCy and Docling are module singletons, never loaded at API boot) and
  both expensive artifacts are cached: layout regions per document + Docling version, dep-SVGs
  by content hash including the spaCy model version.
- Every block records its `line_id` range, so any sentence, token, or entity resolves back to
  page + bbox in the original PDF.
- **Domain NER via a DB-backed EntityRuler.** The stock `de_core_news_lg` NER (PER/LOC/ORG/MISC,
  trained on news) is near-blind on Baubeschreibung vocabulary — `Asphaltbeton AC` guesses LOC,
  `Bauablaufplan` nothing. An `entity_ruler` pipe, compiled from the `entity_rules` table (label +
  spaCy pattern JSONB + optional `pattern_id`, seeded once from a 240-rule authored fixture across
  14 domain labels), runs after the stock `ner` with `overwrite_ents=True` so domain rules win over
  generic mispredictions. Rules are CRUD-managed live from the **Entity Rules** admin page; every
  write is validated against a scratch spaCy pipeline before it persists, and flips an in-process
  dirty flag (the API is single-process — no version table needed) so the next `analyze`/`render`
  rebuilds the pipe from the current enabled set. No restart, no redeploy to change a pattern.
- **Entities are computed in the same pass** as sentences and POS: `AnalyzeResponse.entities`
  groups every hit by label with per-occurrence text, sentence, and `pattern_id` provenance, and
  the same pass renders `AnalyzeResponse.ent_html` — a displacy `style=ent` highlight over the whole
  included text, so the highlight view and the breakdown are computed from one set of Docs under one
  ruler state and one block filter and can never disagree. The modal's Entities tab shows that
  full-text render (capped at 25vh, scrollable) above a label breakdown that ranks labels by
  frequency and marks each occurrence as a rule hit (its `pattern_id`) or a stock-model guess (none)
  — making wrongly-predicted entities visible rather than silently "fixed". `ent_html` is never
  cached server-side. Generating patterns from Katalog rows is a natural, separately-scoped
  follow-up.

### NER Error Investigation

The Entities/Sentences tabs make mispredictions visible; the error-investigation flow turns each
observed error into a persisted, LLM-analyzed, categorized record — the summary of which *is* the
requirement-3 deliverable ("25 flags: 9 register mismatch, 7 missing rules, 4 tokenization, …").
Two ingredients feed it: ad-hoc text analysis, so LV-register text (telegraphic, verb-final — where
news-trained NER degrades most) can be analyzed at all, and flagging.

```mermaid
flowchart TD
    LV[LV item Langtext + Hinweis] -->|NLP-Analyse action| MODAL[NLP modal, ad-hoc text source]
    MODAL -->|POST /nlp/analyze with text| SPLIT[blank-line split -> PROSE blocks, no reflow]
    SPLIT --> TABS[Sentences / Entities tabs]
    TABS -->|flag occurrence: wrong label / not an entity| FLAG[flag + prose comment]
    TABS -->|select text in sentence: missed entity| FLAG
    FLAG -->|POST /ner-flags| PERSIST[(ner_flags row, analysis pending)]
    PROMPT[(PromptLibrary: ner_fehleranalyse)] --> ANALYZE
    RULES[(entity_rules JSON)] --> ANALYZE
    PERSIST --> ANALYZE[assemble prompt + LLMClient structured call]
    ANALYZE -->|NerFailureCategory + analysis + optional rule| UPDATE[(update row: category, provenance)]
    UPDATE --> DASH[NER Analysis page: category dashboard + list + detail + resolve]
    DASH -.->|suggested rule applied by hand| ADMIN2[Entity Rules admin page]
    ADMIN2 -.->|resolve flag with note| DASH
```

- **Ad-hoc analysis reuses `AnalyzeRequest`**: it now accepts either a `document_uuid` or raw
  `text` (exactly one, model-validated). Text is split on blank lines into PROSE blocks — no Docling,
  no reflow (LV text has no layout geometry) — and flows through the same sentence/POS/entity pass,
  returning the same shape. The modal gains a Document/Free-text source switch; an LV item's
  "NLP-Analyse" action preloads its Langtext + Hinweis.
- **Flags snapshot their context.** A `ner_flags` row stores the full analyzed `source_text`, the
  flagged span (text + offsets) and its sentence, the involved label, the flag-time entity list as
  JSONB, and a nullable LV-item/document link. Flags are point-in-time records — later ruleset edits
  never rewrite them; provenance columns (spaCy model, prompt version, LLM model, timestamp) make the
  vintage explicit.
- **One synchronous LLM analysis per flag.** `POST /ner-flags` persists the flag, then calls the LLM
  via `error_analysis.py`: the seeded, versioned `ner_fehleranalyse` PromptLibrary prompt is rendered
  with the analyzed text, entities with `pattern_id`-or-statistical-model provenance, the flag +
  comment, the spaCy model version, and the full enabled `entity_rules` as JSON. Structured output
  returns a closed-enum `NerFailureCategory` (register_mismatch / missing_rule / rule_error /
  tokenization / model_limitation / ambiguity / other), a prose analysis, and an optional advisory
  rule suggestion. An LLM failure leaves the flag with a null analysis, retriable via
  `POST /ner-flags/{uuid}/analyze` — the human observation is never lost.
- **The dashboard aggregates on the effective category** (a user `category_override` wins over the
  LLM assignment), splits counts by open/resolved, and highlights AMBIGUITY. Closing the loop is a
  status flip with a note ("added rule baustoff_bordstein"); applying a suggested rule goes through
  the Entity Rules admin page by hand — no LLM write-path into the curated ruleset.

## Model Access, Logging, and Tracing

All model traffic — chat completions, embeddings, rerank — goes through one OpenRouter transport
layer. The LLM client streams typed events (text deltas, tool calls, done), enforces structured
output, and distinguishes refusals and truncation as typed errors. Embeddings pass through an
optional Postgres cache keyed by SHA-256 of model, dimension, and text.

Every call is recorded twice: an `openrouter_usage` row (tokens, cost, operation, attribution) and
a `prompt_execution_log` row (full request and response, latency, finish reason). Agent runs open
an OTLP flow span carrying the conversation UUID as the session id, so a conversation's turns —
graph nodes, LLM calls, retrieval calls — group as nested spans in Phoenix.

## Future Enhancements

- **Formblatt 223 rendering** — mapping the six engine Kostenarten and the `*_stunden` labour
  basis into the four 223 columns plus Zeitansatz, per position.
- **Zuschläge (VHB 221/222)** — Baustellengemeinkosten, Allgemeine Geschäftskosten, Wagnis und
  Gewinn on top of the EKT to reach the full Einheitspreis.
- **Machine mobilization costs** — mob/demob rates exist in the machine property bags but no cost
  line consumes them yet; wiring them in would let cost-optimal right-sizing emerge.
- **Growth of the Katalog** — more Leistungen, recipes, and machine/material coverage; the
  intended feedback loop from Nachkalkulation into rates and prices.
