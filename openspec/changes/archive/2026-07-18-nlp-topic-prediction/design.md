## Context

AE.NLP.2.5 evaluation criterion 4 ("predicted topics ... reflect the actual topics or categories") is currently unaddressed anywhere in the project. The course's Part 4 (`tasks/topic-modelling.txt`) teaches unsupervised topic modeling — gensim LDA as the bag-of-words baseline, BERTopic as the embedding-based method — and its hands-on validates discovered topics against the known 20-Newsgroups categories. The project already has a working notebook pattern in `nlp-textsummary/` (jupytext pairing, own dependency set, committed executed outputs, HTML export) and a database with 1,248 LV Normalpositionen carrying a natural category signal in their OZ hierarchy.

## Goals / Non-Goals

**Goals:**

- Close evaluation criterion 4 with a defensible, course-aligned deliverable.
- Discover topics unsupervised, then validate them against ground-truth trade labels — never feed the labels into the models.
- Predict topics for held-out application texts (chat messages, Baubeschreibung sections) with the fitted model.
- Add the "clustered to semantic groups" criterion that strengthens the NER-analysis rubric line.
- Fix the reproducibility gap the summarization notebook was criticized for: declare all direct dependencies explicitly.

**Non-Goals:**

- No application feature: no server routes, no UI, no new tables. The notebook reads existing data only.
- No supervised topic classifier; the labels are for evaluation, not training.
- No re-run requirement for the reviewer — committed outputs are the deliverable, as in `nlp-textsummary`.

## Decisions

**D1 — Corpus is LV Normalpositionen, not conversation chat history.** The live DB holds 9 conversations with 56 user/assistant messages (avg ~350 chars, mixed EN/DE, operational register) — an order of magnitude below what LDA needs for stable co-occurrence statistics and below HDBSCAN's clustering floor, with no ground-truth categories. The 1,248 Normalposition langtexts (avg ~430 chars, 10 projects) match the 20-Newsgroups shape of the course hands-on and carry free labels. The chat history is still used, as the held-out prediction set (D6), which is where "predict the most appropriate topic for given texts" is demonstrated.

**D2 — Unsupervised discovery with post-hoc validation, not a predefined topic list.** Part 4 defines topic modeling as unsupervised; the rubric asks whether predicted topics "reflect the actual" categories, which presupposes discovery followed by comparison. Alternative considered: zero-shot classification against a hand-defined trade list — rejected because it ignores the course content the criterion is testing.

**D3 — Ground-truth label = nearest `Titel` ancestor in the OZ hierarchy, lightly normalized.** Walk `parent_oz` upward per document to the closest `positionstyp = 'Titel'` row. Headings recur across documents but with variants ("Verkehrssicherung" vs "Verkehrs- und Baustellensicherung", "Markierung" vs "Fahrbahnmarkierung"); apply lowercase + a small explicit merge map defined in one visible cell, and keep the raw heading alongside. Positions without a Titel ancestor get an explicit sentinel label and are reported. Alternative considered: top-level OZ group — rejected, those are document-specific (Bauabschnitte, project names), not semantic categories.

**D4 — Corpus text and LDA preprocessing.** Model text is `coalesce(langtext_resolved, langtext)` with `kurztext` prepended (the title-like line adds discriminative vocabulary to short positions). For LDA: spaCy `de_core_news_lg` lemmatization, alphabetic tokens only, German stopwords plus a small domain stoplist (units, boilerplate like "einschl.", "gem."), gensim dictionary with frequency extremes filtered. Topic count chosen from a coherence (`c_v`) sweep over k = 6-10, with the sweep shown. BERTopic gets the raw text — the course explicitly notes it needs minimal preprocessing, and showing the asymmetry is itself course-aligned.

**D5 — BERTopic configuration.** Embeddings: `paraphrase-multilingual-MiniLM-L12-v2`, the same model as the `nlp-textsummary` similarity work, keeping the two notebooks methodologically consistent. UMAP with a fixed `random_state` so committed outputs are reproducible. `min_topic_size` around 15 (1,248 docs / expected 8-15 real trades); tuned once, value and rationale stated in the cell. The HDBSCAN outlier topic (-1) is reported, not hidden — its size is a finding about how much LV text is generic boilerplate.

**D6 — Held-out prediction via `transform()` on the fitted BERTopic model.** Held-out texts: the 56 conversation user/assistant messages (concatenated per conversation into 9 documents, plus shown individually where informative) and the six Baubeschreibung sections extracted exactly as in `nlp-textsummary` (same UUIDs, same `section_text` approach). Each gets predicted topic, representative terms, and probability; a short written pass judges plausibility per text. LDA prediction is shown for the Baubeschreibung sections only (chat register defeats bag-of-words lemma overlap — stating that is part of the comparison).

**D7 — Deliverable layout mirrors `nlp-textsummary/`.** New `nlp-topics/` directory: `nlp_topic_modelling.py` (jupytext percent source), paired `.ipynb` executed top-to-bottom, HTML export, figures as committed PNGs, own `pyproject.toml`. Unlike `nlp-textsummary/pyproject.toml`, all direct imports are declared explicitly (`spacy`, `gensim`, `bertopic`, `sentence-transformers`, `scikit-learn`, `pandas`, `matplotlib`/`plotly`, `sqlalchemy`, `psycopg`), and a short README documents the spaCy model download and DB prerequisite.

**D8 — Alignment metrics: NMI plus a per-topic purity table, computed identically for both models.** NMI is symmetric and robust to differing topic counts; the purity crosstab is the human-readable view the rubric wants ("does topic 3 = Asphaltarbeiten?"). BERTopic outlier documents are excluded from its scores with the exclusion counted and stated, since -1 is "no topic", not a wrong topic.

## Risks / Trade-offs

- [Label noise: Titel headings are inconsistent across documents and some are administrative ("Allgemeines", "Hilfsleistungen") rather than trades] → Keep the merge map small and visible; treat administrative headings as their own categories and discuss them in the interpretation rather than forcing them into trades.
- [HDBSCAN may put a large share of positions into the outlier topic] → Report the share, tune `min_topic_size` once; if outliers exceed ~40%, use BERTopic's `reduce_outliers` and say so.
- [LDA coherence may be flat across k, making the k choice look arbitrary] → Show the sweep and pick the elbow; the point is a justified choice, not an optimal one.
- [Heavy native deps (umap-learn, hdbscan) may be slow to build on macOS/arm64] → Isolated in `nlp-topics/`'s own venv via `uv`; wheels exist for py3.12/arm64.
- [Held-out chat set is tiny and partly English] → Framed as a demonstration of `transform()` on genuinely unseen, register-shifted text, not as an evaluation; the multilingual embedding model is the mitigation and the observation.
- [Notebook depends on the developer's local Postgres, so a grader cannot re-run it] → Same accepted trade-off as `nlp-textsummary`: committed executed outputs + HTML export are the reviewable artifact.

## Open Questions

- None blocking. If the coherence sweep and BERTopic's natural topic count disagree strongly, the interpretation section discusses it rather than forcing agreement.
