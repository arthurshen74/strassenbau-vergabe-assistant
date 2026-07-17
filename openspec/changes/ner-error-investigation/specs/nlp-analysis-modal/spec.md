# Spec delta: nlp-analysis-modal

## MODIFIED Requirements

### Requirement: Modal opens from a document picker with three tabs
The UI SHALL provide an NLP analysis modal whose text source is either an analyzable document (listed grouped by project) or ad-hoc text: free text pasted into the modal, or an LV item's Langtext and Hinweis passed in when the modal is opened from an LV item's "NLP-Analyse" action. Selecting a source shows the analysis tabs (Text, Sentences, POS, Entities).

#### Scenario: Opening
- **WHEN** the user opens the NLP modal and picks a Baubeschreibung
- **THEN** the Text tab shows its reflowed text

#### Scenario: Opening from an LV item
- **WHEN** the user triggers "NLP-Analyse" on an LV position with Langtext and Hinweis
- **THEN** the modal opens with that text preloaded and analyzed, no document selected

#### Scenario: Pasting free text
- **WHEN** the user switches the modal to free-text mode and pastes a paragraph
- **THEN** the tabs show the analysis of the pasted text

## ADDED Requirements

### Requirement: Text can be selected and flagged as a missed entity
Within a sentence in the Sentences tab, the user SHALL be able to select a span of text and flag it as a missed entity, choosing the expected label and entering a comment. Selections spanning multiple sentences SHALL be rejected with a hint.

#### Scenario: Flagging a miss
- **WHEN** the user selects `Bordstein` inside one sentence and submits the missed-entity flag form with label BAUSTOFF and a comment
- **THEN** a MISSED_ENTITY flag is created for that span and its sentence

#### Scenario: Cross-sentence selection rejected
- **WHEN** the user's selection crosses a sentence boundary
- **THEN** the flag affordance is disabled with a hint to select within one sentence
