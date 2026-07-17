# Spec delta: nlp-entities-tab

## ADDED Requirements

### Requirement: Entity occurrences can be flagged from the tab
Each occurrence row in the Entities tab SHALL offer a flag action opening a small form: flag kind (WRONG_LABEL or NOT_AN_ENTITY), expected label (for WRONG_LABEL), and a required comment; submitting creates the flag and shows the analysis result state inline.

#### Scenario: Flagging a wrong label from the tab
- **WHEN** the user flags the occurrence `Asphaltbeton AC` (LOC, no pattern id) as WRONG_LABEL expecting BAUSTOFF, with a comment
- **THEN** the flag is created carrying the occurrence's span, sentence, and provenance, and the row indicates its flagged state

#### Scenario: Already-flagged occurrence indicated
- **WHEN** an occurrence has an existing open flag in the current session's view
- **THEN** the row shows a flagged indicator instead of offering a duplicate flag action
