# Spec delta: nlp-analysis-modal

## REMOVED Requirements

### Requirement: Modal opens from a document picker with three tabs

Removed: the modal no longer offers any in-modal source selection (document picker, free-text mode, source toggle). Replaced by "Modal opens preloaded with exactly one source".

## ADDED Requirements

### Requirement: Modal opens preloaded with exactly one source

The NLP analysis modal SHALL NOT contain a document picker, a free-text input, or a source toggle. It SHALL open only via a launch action that fixes its source: a document (from a Baubeschreibung's "NLP-Analyse" action in the Project Documents tab) or ad-hoc text (an LV item's Langtext and Hinweis from its "NLP-Analyse" action). The active source SHALL be labeled in the modal (file name, or the LV reference). The analysis tabs (Text, Sentences, POS, Entities) run over the preloaded source immediately.

#### Scenario: Opening from the Documents tab

- **WHEN** the user clicks "NLP-Analyse" on an ingested Baubeschreibung row in the Project Documents tab
- **THEN** the modal opens on that document, the Text tab shows its reflowed text, and no source controls are shown

#### Scenario: Opening from an LV item

- **WHEN** the user triggers "NLP-Analyse" on an LV position with Langtext and Hinweis
- **THEN** the modal opens with that text preloaded and analyzed, labeled with the LV reference

#### Scenario: No bare launch

- **WHEN** the user looks for a global "NLP Analysis" command (sidebar)
- **THEN** none exists — the modal is reachable only through a source's launch action

### Requirement: The Project Documents tab offers an NLP launch per analyzable document

In the Project Documents tab, each PROSE_DOCUMENT row whose ingest has produced source lines SHALL show an "NLP-Analyse" launch action alongside the existing row actions. LV_DOCUMENT rows and PROSE_DOCUMENT rows without extracted source lines SHALL NOT show the action.

#### Scenario: Analyzable row

- **WHEN** a Baubeschreibung has completed ingest
- **THEN** its row shows the "NLP-Analyse" action, and clicking it opens the modal on that document

#### Scenario: Non-analyzable rows

- **WHEN** a row is an LV_DOCUMENT, or a Baubeschreibung whose ingest has not produced source lines
- **THEN** the row shows no "NLP-Analyse" action
