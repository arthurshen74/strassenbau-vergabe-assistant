# Spec delta: nlp-entities-tab

## MODIFIED Requirements

### Requirement: Analysis responses include an aggregated entity view

The `/nlp/analyze` response SHALL include, alongside sentences and POS statistics, entity statistics: for each label found, its occurrence count and the list of occurrences (text, sentence reference, pattern id if rule-derived). The response SHALL additionally include `ent_html`: the displacy `style=ent` HTML rendered over the full analyzed text (the included blocks), produced in the same analysis pass from the same Docs as the entity statistics, so the highlight view and the breakdown can never disagree on ruler state or block filter. `ent_html` SHALL NOT be cached server-side.

#### Scenario: Entities computed alongside sentences and POS

- **WHEN** an analysis request completes
- **THEN** the response's `entities` field lists every label found across the included blocks, sorted by descending count

#### Scenario: Full-text render matches the breakdown

- **WHEN** an analysis response reports an occurrence of `AC 11 D S` under BAUSTOFF
- **THEN** the response's `ent_html` contains that same span highlighted with the BAUSTOFF label

## ADDED Requirements

### Requirement: The Entities tab shows the full-text entity render above the breakdown

The Entities tab SHALL render the response's `ent_html` above the label/occurrence breakdown, in a container with small typography (Tailwind `text-sm`), a maximum height of `25vh`, and a vertical scrollbar when the content overflows. When the analysis found no entities, the pane SHALL be omitted and the existing empty state shown.

#### Scenario: Render pane on top

- **WHEN** the user opens the Entities tab for an analyzed Baubeschreibung
- **THEN** the displacy entity highlights for the whole included text appear above the label frequency list, capped at 25vh with vertical scrolling

#### Scenario: Overflowing document

- **WHEN** the analyzed text's ent render is taller than 25vh
- **THEN** the pane scrolls vertically within its cap instead of pushing the breakdown off-screen
