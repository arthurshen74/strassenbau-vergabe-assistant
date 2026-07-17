# Tasks: lv-langtext-unwrap

## 1. Implementation

- [x] 1.1 Add `unwrapSoftBreaks` to `ui/src/views/main/lvNlpPreset.ts` (paragraph split on blank lines, line joins with the reflow German dehyphenation rule, collapse space runs, trim, drop empty paragraphs) and apply it to Langtext and Hinweis in `nlpSourceForLvItem`

## 2. Verification

- [x] 2.1 `tsc` + `vite build` clean
- [x] 2.2 Browser smoke on an LV item with hard-wrapped Langtext (e.g. LV OZ 00.07.0001): Text tab shows unwrapped paragraphs with preserved blank-line breaks; Sentences tab segments the merged paragraphs correctly; Hinweis still a separate block
