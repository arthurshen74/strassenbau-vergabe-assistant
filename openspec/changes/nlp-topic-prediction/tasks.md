## 1. Scaffolding

- [ ] 1.1 Create `nlp-topics/` with `pyproject.toml` declaring all direct deps (spacy, gensim, bertopic, sentence-transformers, scikit-learn, pandas, matplotlib, plotly, sqlalchemy, psycopg, jupytext, jupyterlab) and a short README (spaCy model download, DB prerequisite, how to read without running)
- [ ] 1.2 `uv sync` the notebook venv, download `de_core_news_lg`, verify bertopic/umap/hdbscan import on py3.12/arm64
- [ ] 1.3 Create `nlp_topic_modelling.py` (jupytext percent) with header markdown framing criterion 4, the course Part 4 method, and the corpus-substitution rationale; pair to `.ipynb`

## 2. Corpus and labels

- [ ] 2.1 Load Normalpositionen from Postgres: oz, kurztext, `coalesce(langtext_resolved, langtext)`, document/project refs; build model text as kurztext + langtext
- [ ] 2.2 Derive `trade_label` per position via nearest `Titel` ancestor walk (`parent_oz` chain per document); sentinel label for positions without one
- [ ] 2.3 Add the visible label-normalization cell (lowercase + small merge map for heading variants); print corpus size and label distribution table

## 3. LDA baseline

- [ ] 3.1 Preprocess for LDA: spaCy lemmatization, alphabetic-only, German stopwords + domain stoplist; gensim dictionary with extremes filtered
- [ ] 3.2 Coherence (`c_v`) sweep k = 6-10, plot, pick and justify k
- [ ] 3.3 Fit final LDA; display top terms per topic and per-document dominant topic

## 4. BERTopic

- [ ] 4.1 Fit BERTopic on raw texts with `paraphrase-multilingual-MiniLM-L12-v2`, fixed UMAP `random_state`, `min_topic_size` ~15 with rationale stated
- [ ] 4.2 Display `get_topic_info()` incl. outlier topic share; apply and document `reduce_outliers` if outliers exceed ~40%
- [ ] 4.3 Render `visualize_topics` and `visualize_barchart` (export static PNGs for the committed figures)

## 5. Validation against trade labels

- [ ] 5.1 Topic-by-label crosstab for both models (BERTopic outliers excluded and counted)
- [ ] 5.2 Compute NMI + per-topic purity identically for both models; summary comparison table

## 6. Held-out topic prediction

- [ ] 6.1 Load held-out texts: 9 conversations (user/assistant messages concatenated per conversation) and the six `nlp-textsummary` Baubeschreibung sections (same UUIDs and section extraction)
- [ ] 6.2 `transform()` held-out texts with BERTopic; show excerpt, predicted topic terms, probability; LDA prediction for the Baubeschreibung sections
- [ ] 6.3 Write the per-text plausibility assessment (the criterion's "predicted topics are logical" evidence)

## 7. Interpretation and delivery

- [ ] 7.1 Write the LDA-vs-BERTopic discussion: which aligns better with actual trades and why, referencing scores and concrete topics; answer the course's "why is one performing better?"
- [ ] 7.2 Execute the notebook top-to-bottom, verify every cell has outputs, commit-ready `.ipynb` + PNGs; export the HTML read-only version
- [ ] 7.3 Update `AE.NLP.2.5.README.md`: map criterion 4 (and the "clustered to semantic groups" criterion) to `nlp-topics/`, add it to the file inventory and run instructions
