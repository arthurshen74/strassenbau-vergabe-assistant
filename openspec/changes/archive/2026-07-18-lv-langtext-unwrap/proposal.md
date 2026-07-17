# Proposal: lv-langtext-unwrap

## Why

LV Langtext (and Hinweis) come out of GAEB with fixed-width hard line wraps: a single sentence arrives as several physical lines broken mid-clause ("Mehrmaliger bzw. zwischenzeitlicher Abbau und Räumung\nsowie Umsetzung der Baustelle …"). In the NLP modal's LV mode those soft wraps show as ragged line breaks in the Text tab, and the same wrapped string is what gets analyzed and snapshotted onto NER flags. The breaks carry no meaning — they are layout artifacts of the GAEB fixed-width format.

## What Changes

Unwrap soft line breaks when composing the LV source text for the NLP modal (`nlpSourceForLvItem`):

- Paragraphs are split on blank lines (`\n\n+`) — these are real semantic breaks and are preserved (they also delimit PROSE blocks in the ad-hoc analyze path).
- Within a paragraph, single `\n` becomes a single space; runs of spaces collapse.
- Langtext and Hinweis are each unwrapped, then joined with a blank line as today.

Because the transformation happens at source composition, the Text tab display, the `POST /nlp/analyze` request, and any flag's `source_text`/sentence snapshots all see the same unwrapped text — no divergence between what is shown, analyzed, and persisted.

- Line-end hyphens are dehyphenated with the same German rule the reflow pipeline uses: dropped when the continuation starts lowercase ("anpas-\nsen" → "anpassen"), kept when it starts uppercase. Hyphenated wraps are present in the LV data (e.g. OZ 00.07.0001, project L 24 OD Haldensleben).

Out of scope: document mode and the server-side ad-hoc text handling are untouched.

## Capabilities

### Modified

- **`nlp-analysis-modal`** — the LV launch requirement gains the unwrap behavior: the composed LV source text has soft wraps joined, blank-line paragraph breaks preserved.

## Impact

- UI only: `ui/src/views/main/lvNlpPreset.ts` (unwrap function + use) and a unit test for it.
- No backend, DB, API, or type-generation changes.
