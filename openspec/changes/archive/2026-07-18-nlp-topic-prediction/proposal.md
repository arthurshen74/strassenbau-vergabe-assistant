## Why

The AE.NLP.2.5 evaluation criteria grade whether "predicted topics for selected set of text are logical and reflect the actual topics or categories" — and nothing in the project predicts topics today. The course's Part 4 (`tasks/topic-modelling.txt`) prescribes unsupervised topic modeling (LDA baseline, then BERTopic) validated against known categories, mirroring its 20-Newsgroups hands-on. Closing this gap also strengthens the "NER analysis with at least two criterions" rubric line by adding the "clustered to semantic groups" criterion.

## What Changes

- New self-contained analysis notebook directory `nlp-topics/`, sibling to `nlp-textsummary/`, following the same conventions: jupytext-paired `.py` source, own `pyproject.toml`, executed `.ipynb` with committed outputs, rendered HTML export.
- Corpus: the 1,248 LV `Normalposition` langtexts from the live Postgres database (avg ~430 chars, 10 projects), each labeled with its nearest `Titel` ancestor in the OZ hierarchy as ground-truth category (recurring trades: Baustelleneinrichtung, Verkehrssicherung, Asphaltarbeiten, Markierung/Beschilderung, ...).
- Two topic models, per the course content: gensim LDA on lemmatized bag-of-words as the baseline, and BERTopic with the multilingual SBERT model already used in `nlp-textsummary` (`paraphrase-multilingual-MiniLM-L12-v2`).
- Validation of discovered topics against the ground-truth trade labels: topic-by-label crosstab, purity/NMI, BERTopic visualizations.
- Topic prediction on held-out texts: the stored conversation chat messages and the six Baubeschreibung sections from `nlp-textsummary`, assigned a topic by the fitted model and sanity-read for plausibility.
- Interpretation section comparing LDA vs BERTopic on short technical German text, answering the course's "why is one performing better?" question.
- `AE.NLP.2.5.README.md` updated to map the topic-prediction evaluation criterion to the new notebook.

## Capabilities

### New Capabilities

- `topic-modelling-notebook`: unsupervised topic discovery (LDA + BERTopic) over the LV-position corpus, validated against OZ-hierarchy trade labels, with topic prediction for held-out application texts.

### Modified Capabilities

<!-- none — no application runtime behavior changes; the notebook only reads existing data -->

## Impact

- New directory `nlp-topics/` (notebook, jupytext source, pyproject, HTML export, figures). No server or UI code changes.
- Reads the live Postgres database (`lv_items`, `conversations`/`messages`) and reuses `server/shared` reflow imports read-only, as `nlp-textsummary` already does.
- New notebook-local dependencies: `gensim`, `bertopic` (pulls umap-learn/hdbscan), `sentence-transformers`, `spacy`, plus plotting; isolated in `nlp-topics/pyproject.toml`, not the root project.
- `AE.NLP.2.5.README.md` gains a Requirement/criterion mapping section for topic prediction.
