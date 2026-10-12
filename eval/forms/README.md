# Formblatt ground truth

Hand-made labels for the checkbox state of Vergabestelle Formblätter and for the facts a
Kalkulator reads off them. They measure the form pipeline (task 08: toggle detection and
chunks that carry only checked options) before and after a change. Nothing in the product
reads these files.

## Layout

```
eval/forms/
  labels/<tender>/<pdf-stem>.json   one file per labelled PDF: box state per extracted line
  facts/<tender>.json               one file per tender: fact questions with gold answers
  .cache/                           rendered page PNGs of the labeler (gitignored)
```

The tender name is the folder name of the extracted ZIP in `server/training`; `pdf` is the
path of the PDF inside that folder.

## Label schema (`labels/`)

```json
{
  "tender": "NOO-2026-0304_10BW62-1",
  "pdf": "Heftung 1 Angebotsaufforderung/HVA_B_StB_111_Vorlage_Aufforderung_zur_Angebotsabgabe.pdf",
  "form_id": "HVA B-StB 111",
  "kind": "flattened",
  "labelled_pages": [1, 2, 3, 4, 5],
  "lines": [
    {"page": 3, "bbox": [104.881, 482.283, 468.231, 495.103],
     "text": "Nebenangebote sind nicht zugelassen; Nr. 4 der Teilnahmebedingungen gilt nicht.",
     "state": "checked"}
  ]
}
```

- A line is one `<line>` of `pdftotext -bbox-layout`, exactly as `extract_source_lines`
  emits it (top-origin bbox in points). Tick glyphs ("X", "×") and section numbers often
  come out as lines of their own; they are never labelled, the state belongs to the label
  line the box sits in front of. Where `pdftotext` merged the glyph into the label line, the
  text keeps it ("X nicht zugelassen.").
- `state` is `checked` or `unchecked`; lines without a box are not written (`none`).
- A box without a text line on its row (the empty "sonstige" rows) is not labelled.
- `labelled_pages` lists the pages that were confirmed; a confirmed page with no boxes has
  no lines. Only confirmed pages are scored.
- `kind` is `xfa`, `acroform` or `flattened` (zero AcroForm fields plus a Formblatt id in
  the filename). Dynamic XFA forms render as the Adobe placeholder page, so they carry no
  box labels; their facts are labelled from the pipeline's XFA extraction.

## Fact schema (`facts/`)

```json
{
  "tender": "NOO-2026-0304_10BW62-1",
  "facts": [
    {"key": "nebenangebote_zugelassen",
     "question": "Sind Nebenangebote für dieses Projekt zugelassen?",
     "kind": "yes_no", "gold": "nein",
     "source": {"pdf": "Heftung 1 Angebotsaufforderung/HVA_B_StB_111_....pdf", "page": 3,
                "section": "6 Nebenangebote"}}
  ]
}
```

`kind` is `yes_no` (gold `ja`/`nein`), `value` (a short string the answer must contain) or
`list` (every string must be contained). The Fundstelle is always a Vergabestelle form, even
when a prose document repeats the fact. A fact without `gold` is skipped by the script.

## The labeler

```bash
uv sync --group tools
uv run --group tools streamlit run server/scripts/form_labeler/app.py
```

Sidebar: tender, the forms of the tender (Vergabestelle and UNBEKANNT first, Bieter forms
last; a green check marks a fully confirmed form), page navigation. Main: the page image
next to one radio per extracted line (`–` no box, `☐` unchecked, `☒` checked). Proposals
from a geometric aid (`proposals.py`: pdfplumber squares, tick glyphs or strokes inside,
AcroForm widget state, nearest line to the right) are shown in orange until the page is
confirmed with "Seite bestätigen", which writes the file and jumps to the next unconfirmed
page. The "Fakten" tab edits the fact file; `FORM_LABELER_CORPUS` points the tool at a
different corpus directory.

## The measurement script

```bash
PYTHONPATH=server uv run python -m scripts.eval_form_labels --boxes --detector none
PYTHONPATH=server uv run python -m scripts.eval_form_labels --boxes \
    --detector shared.services.ingestion.forms.flattened:find_boxes
PYTHONPATH=server uv run python -m scripts.eval_form_labels --facts --modality plus --bm25 \
    --project-map WNAB-SB7-12-2026-VOB-EU-B=<project uuid>
```

`--boxes` runs the detector (`pdf_bytes -> list[Toggle]`) plus the pipeline's
`merge_marginal_tokens` and `attach_toggles` on every labelled PDF and matches each detected
option line to a label by page, bbox overlap and text containment (so a merged line "6.1
Nebenangebote ..." still matches the label on the original line). The table shows per form
family: labelled boxes, detected boxes, true positives (matched with the same state),
wrong-state matches, false positives, misses, precision, recall; then every miss, false
positive and wrong state with page and text. `--detector none` prints the label statistics
only.

`--facts` resolves each tender to a project of the running stack (`vergabe_id` or
`project_name` against the tender folder name, `--project-map` to override), opens one
`project_chat` conversation per repetition (`form-eval-<tender>-<n>`), asks every gold fact
with the retrieval config from the command line and grades the stored assistant message:
`yes_no` by the first ja/nein word, `value`/`list` by case-insensitive containment. The table
shows per tender how many facts were correct in every run, in some runs, in none; then the
full answers of every fact that was not correct in all runs. `--delete-conversations`
removes the probe conversations afterwards. Exit code is always 0; this is a report.
