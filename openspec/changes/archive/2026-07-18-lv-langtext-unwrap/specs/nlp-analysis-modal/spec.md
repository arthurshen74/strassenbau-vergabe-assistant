# Spec delta: nlp-analysis-modal

## ADDED Requirements

### Requirement: LV source text is unwrapped before analysis

When composing the modal source from an LV item, soft line wraps SHALL be removed: within a blank-line-separated paragraph, single line breaks become single spaces (with whitespace runs collapsed); blank lines SHALL be preserved as paragraph separators. A line-end hyphen SHALL be dehyphenated with the reflow rule: dropped and joined directly when the next line starts lowercase, kept (joined with a space) when it starts uppercase. Langtext and Hinweis SHALL each be unwrapped and remain separated by a blank line. The unwrapped text SHALL be the single source used for the Text tab display, the analysis request, and any flag snapshots created from it.

#### Scenario: Hard-wrapped GAEB paragraph

- **WHEN** an LV Langtext contains a sentence hard-wrapped across five lines ("Mehrmaliger bzw. zwischenzeitlicher Abbau und Räumung\nsowie Umsetzung der Baustelle …")
- **THEN** the modal's Text tab shows it as one continuous paragraph and the analysis receives the unwrapped text

#### Scenario: Dehyphenation

- **WHEN** the Langtext wraps a word with a hyphen ("… an die neue planmäßige Höhe anpas-\nsen.")
- **THEN** the unwrapped text reads "… an die neue planmäßige Höhe anpassen."

#### Scenario: Paragraph breaks survive

- **WHEN** the Langtext contains blank-line-separated paragraphs and a Hinweis is appended
- **THEN** each paragraph and the Hinweis remain separate blank-line-delimited blocks (distinct PROSE blocks in the analysis)

#### Scenario: Flag snapshots use unwrapped text

- **WHEN** the user flags an entity in an LV-launched analysis
- **THEN** the flag's `source_text` snapshot contains the unwrapped text, matching what was displayed and analyzed
