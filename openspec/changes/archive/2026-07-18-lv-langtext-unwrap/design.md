# Design: lv-langtext-unwrap

## Decisions

### D1: Unwrap at source composition (UI), not server-side

The transformation lives in `nlpSourceForLvItem` (`ui/src/views/main/lvNlpPreset.ts`), the single place the LV modal source string is composed. Everything downstream — the Text tab display, the `POST /nlp/analyze` request, the flag `source_text`/sentence snapshots — flows from that one string, so all three stay consistent by construction. A server-side transform in `_blocks_from_text` would fix only the analysis while the Text tab and flag snapshots kept showing the wrapped raw text.

### D2: The unwrap rule

```
unwrapSoftBreaks(text):
  split on /\n\s*\n+/          -> paragraphs (blank lines are semantic; also the
                                  PROSE-block delimiter in the ad-hoc analyze path)
  within each paragraph:
    replace /\s*\n\s*/ with " " -> soft wraps become single spaces
    collapse runs of spaces
    trim
  drop empty paragraphs, join with "\n\n"
```

Langtext and Hinweis are each unwrapped independently, then joined with `"\n\n"` exactly as today, so Hinweis remains its own PROSE block.

Short stacked lines ("Frostschutzschicht herstellen.\nIn Verkehrsflächen …") merge into one paragraph of short sentences — spaCy segments them correctly on the terminal periods, so nothing is lost.

### D3: German dehyphenation, same rule as reflow

Hyphenated wraps DO occur in LV Langtext (e.g. OZ 00.07.0001 in project L 24 OD Haldensleben: "anpas-\nsen", "aus-\nführen" — found during implementation, revising the initial no-dehyphenation assumption). `unwrapSoftBreaks` therefore ports the reflow rule verbatim: a line-end hyphen joins the next line dropping the hyphen when the continuation starts lowercase (justification break), keeping it when it starts uppercase (compound like "SRT-Pendel"). Known accepted limitation, same as reflow: a wrapped Ergänzungsstrich ("Beton-\nund Asphalt") would merge incorrectly — accepted there, accepted here for consistency.

### D4: No new test infrastructure

The UI has no unit-test runner (no vitest), and introducing one for a single pure function is out of proportion. Verification is `tsc` + `vite build` plus a browser smoke against an LV item known to have wrapped Langtext (e.g. LV OZ 00.07.0001 from the screenshot), confirming the Text tab shows unwrapped paragraphs and sentence segmentation is unchanged or improved.
