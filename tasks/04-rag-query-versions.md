# Task 04: Versioned, editable RAG queries for project info

Depends on: nothing. Parallel with 01, 02, 03. Task 05 consumes the repository.

## Goal

A `rag_query_versions` table holds the questions the project-info step asks, one row per
`(query_key, language, version)`, append-only. A seed script loads the initial German set.
An API and a small editor view let a user read the latest version per key, see the
history, and publish a new version.

## Model

`ProjectInfoQuery(StrEnum)` in `server/shared/models/enums.py`, value = `query_key`, with
the target column recorded next to it in code (a module-level mapping in the new service
package of task 05; for this task define the enum and the mapping in
`server/shared/models/rag_query.py` so task 05 can import it):

| query_key | target `projects` column |
|---|---|
| `project-description` | `project_description` |
| `project-massnahmenummer` | `massnahmenummer` |
| `project-name` | `project_name` |
| `project-vergabenummer` | `vergabe_id` |
| `project-bauleistung` | `bauleistung` |
| `project-location` | `location` |

Table `rag_query_versions` (`server/shared/db/tables/rag_query_versions.py`, register in
`tables/__init__.py`, UoW attribute `rag_queries`):

| column | type | notes |
|---|---|---|
| `rag_query_version_uuid` | uuid PK | `gen_random_uuid()` |
| `query_key` | text NOT NULL | CHECK built from `ProjectInfoQuery` |
| `language` | text NOT NULL | ISO 639-1, lower case; CHECK `language ~ '^[a-z]{2}$'` |
| `version` | integer NOT NULL | starts at 1 per (key, language) |
| `name` | text NOT NULL | display name |
| `description` | text NOT NULL | what the query is for |
| `query_text` | text NOT NULL | retrieval question (embedding + BM25 input) |
| `answer_instruction` | text NOT NULL | output rule for the synthesis LLM |
| `created_at` | timestamptz NOT NULL | `now()` |

Unique `(query_key, language, version)`. Migration `sql/19_rag_query_versions.sql`.

Pydantic (`server/shared/models/rag_query.py`): `RagQueryVersion` (full row,
`from_attributes`), `NewRagQueryVersion` (no uuid/version/created_at). API DTOs
(`server/shared/models/rag_query_schema.py`): `RagQueryVersionRead`,
`RagQueryVersionCreate` (`name`, `description`, `query_text`, `answer_instruction`, all
`min_length=1`; `language` defaulting to `settings.project_info_language`). Add both to
`BODY_MODELS` in `server/scripts/export_schema.py`.

Settings: `project_info_language: str = "de"` in `server/shared/config.py`; add
`PROJECT_INFO_LANGUAGE=de` to `.env.example` under Miscellaneous with a one-line comment.
(Task 05 also needs this setting; whichever lands first adds it, the other checks.)

## Repository

`server/shared/repositories/rag_queries.py::RagQueryVersionRepository(conn)`:
- `add(new: NewRagQueryVersion) -> RagQueryVersion`: version = `COALESCE(MAX(version), 0)
  + 1` for the (key, language) in the same statement (insert ... select) so concurrent
  publishes cannot collide; on a unique violation let it propagate.
- `get_latest(query_key, language) -> RagQueryVersion | None`.
- `latest_all(language) -> list[RagQueryVersion]` (one row per key, `DISTINCT ON`).
- `history(query_key, language) -> list[RagQueryVersion]` newest first.
Mirror `PromptVersionRepository` for style.

## Seed

`server/scripts/seed/rag_queries/` package with `__main__.py` and one file per key,
`<query_key>.<language>.yaml` (`name`, `description`, `query_text`, `answer_instruction`).
Seeding is append-only and not idempotent, exactly like prompt seeding: every run publishes
a new version of every file. Document the command in `DEVOPS.md` next to prompt seeding:
`PYTHONPATH=server uv run python -m scripts.seed.rag_queries`.

Initial German set (edit freely for tone, keep the two-text split):

- `project-description` / "Projektbeschreibung" / "Kurzbeschreibung der Maßnahme für die
  Projektübersicht."
  - query_text: `Worum geht es bei dieser Baumaßnahme? Art der Bauleistung, Straße bzw.
    Abschnitt, Umfang und wesentliche Arbeiten laut Baubeschreibung und Leistungsverzeichnis.`
  - answer_instruction: `Fasse die Maßnahme in 2 bis 4 Sätzen zusammen (Art der Arbeiten,
    Ort/Strecke, Umfang). Keine Aufzählung, keine Einleitung, keine Quellenangaben.`
- `project-massnahmenummer` / "Maßnahmenummer"
  - query_text: `Welche Maßnahmenummer (Projektnummer, Maßnahme-Nr., Bauvorhaben-Nr.) trägt
    diese Baumaßnahme laut Deckblatt oder Aufforderung zur Angebotsabgabe?`
  - answer_instruction: `Gib nur die Maßnahmenummer wörtlich zurück, ohne Zusatz. Wenn
    mehrere Nummern genannt sind, die vom Auftraggeber als Maßnahme-/Projektnummer
    bezeichnete.`
- `project-name` / "Maßnahme (Projektname)"
  - query_text: `Wie lautet die Bezeichnung der Baumaßnahme (Titel der Maßnahme) auf dem
    Deckblatt der Vergabeunterlagen?`
  - answer_instruction: `Gib nur den Titel der Maßnahme zurück, wie er in den Unterlagen
    steht (Straße, Ortslage, Art der Maßnahme). Keine Vergabenummer, kein Zusatztext.`
- `project-vergabenummer` / "Vergabenummer"
  - query_text: `Welche Vergabenummer (Vergabe-Nr., Ausschreibungsnummer, Verfahrensnummer)
    hat dieses Vergabeverfahren?`
  - answer_instruction: `Gib nur die Vergabenummer wörtlich zurück, ohne Zusatz.`
- `project-bauleistung` / "Bauleistung"
  - query_text: `Wie wird die zu vergebende Bauleistung in der Aufforderung zur
    Angebotsabgabe bzw. auf dem Deckblatt bezeichnet?`
  - answer_instruction: `Gib nur die Bezeichnung der Bauleistung zurück, wie sie im Dokument
    steht. Kein Zusatztext.`
- `project-location` / "Baustelle (nächster Ort)"
  - query_text: `Wo liegt die Baustelle? Ortslage, Gemeinde, Straße und Abschnitt (von/bis,
    Netzknoten oder Stationierung) laut Baubeschreibung.`
  - answer_instruction: `Nenne nur den nächstgelegenen Ort (Stadt oder Gemeinde) zur
    Baustelle, ggf. mit Ortsteil, so dass er geokodierbar ist. Bei mehreren gleich nahen
    Orten wähle den, der im Titel der Maßnahme genannt ist. Keine Erklärung.`

## API

`server/api/routes/rag_queries.py`, prefix `/rag-queries`, registered in `api/main.py`:
- `GET /rag-queries?language=de` -> `list[RagQueryVersionRead]` (latest per key; keys
  without a row for that language are simply absent).
- `GET /rag-queries/{query_key}/history?language=de` -> `list[RagQueryVersionRead]`.
- `POST /rag-queries/{query_key}` body `RagQueryVersionCreate` -> 201
  `RagQueryVersionRead`. `query_key` is typed as `ProjectInfoQuery` so an unknown key is a
  422 from FastAPI.
Logic in `server/shared/services/rag_query_service.py` (thin: validates nothing beyond the
DTOs, maps rows to DTOs).

## UI

- `ui/src/api/ragQueries.ts`: `ragQueryKeys`, `useRagQueries(language)`,
  `useRagQueryHistory(key, language)`, `usePublishRagQuery(key)`.
- Sidebar command "RAG Queries" (`ui/src/components/layout/Sidebar.tsx` `COMMANDS`, a new
  `MainWindowKind` `'rag_queries'` in `ui/src/store/mainWindow.ts`, plus the dispatch
  mapping if `view_*` commands are enumerated there) opening
  `ui/src/views/main/RagQueriesView.tsx`. Look at how the existing "View Prompts" command and
  its view are wired and mirror that exactly.
- The view: language selector (text input or small select, default from a constant
  `DEFAULT_RAG_QUERY_LANGUAGE = 'de'` in the view; the server default is authoritative for
  ingestion), a list of the six keys with name + version + description, an edit panel with
  `name`, `description`, `query_text` (textarea), `answer_instruction` (textarea) and a
  "Publish new version" button, and a collapsible history showing earlier versions
  read-only. Publishing refetches the list. Keep it one file under ~400 lines; split the
  history list into its own component if it grows.

## Tests

- `tests/unit/models/test_dtos.py`: add the new DTOs to `ALL_DTOS`.
- `tests/integration/repositories/test_rag_queries.py`: version numbering per (key,
  language); `latest_all` returns one per key; history order; two languages do not share
  version counters.
- `tests/integration/api/test_rag_queries_api.py`: list empty -> publish -> list shows v1 ->
  publish again -> v2 and history length 2; unknown key 422; empty `query_text` 422.
- Seed: a unit test that every `.yaml` under the seed package parses into
  `NewRagQueryVersion` and that every `ProjectInfoQuery` key has a `de` file.

## Docs

- `APPLICATION_ARCHITECTURE.md`: ERD entity `rag_query_versions`; data-model note that
  queries are versioned like prompts.
- `DEVOPS.md`: seeding command, `PROJECT_INFO_LANGUAGE`.
- `GLOSSARY.md`: "RAG Query (Projektinfo)" entry.

## Done when
- Seeded, listed, edited and re-listed through the UI; history shows both versions.
- `get_latest` and `latest_all` are ready for task 05.
