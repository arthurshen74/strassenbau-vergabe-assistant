# topic-modelling-notebook Specification

## Purpose
Self-contained analysis notebook (`nlp-topics/`) for unsupervised topic discovery over the LV-position corpus: gensim LDA baseline and BERTopic on multilingual embeddings, validated against OZ-hierarchy trade labels, with topic prediction for held-out application texts.

## Requirements

### Requirement: LV-position corpus with ground-truth trade labels
The notebook SHALL load all LV items with `positionstyp = 'Normalposition'` from the Postgres database and label each position with its nearest ancestor `Titel` row in the OZ hierarchy of the same document. Positions whose ancestor chain contains no `Titel` SHALL be labeled with a sentinel category and reported, not dropped silently. The notebook SHALL print the corpus size and the label distribution before any modeling.

#### Scenario: Corpus assembly
- **WHEN** the corpus cell runs against the live database
- **THEN** it yields one record per Normalposition with `oz`, `kurztext`, `langtext`, document reference, and a `trade_label` derived from the nearest Titel ancestor, and prints corpus size plus a label-frequency table

#### Scenario: Position without a Titel ancestor
- **WHEN** a Normalposition has no `Titel` ancestor in its document's OZ hierarchy
- **THEN** it receives the sentinel label and is counted in the printed label distribution

### Requirement: LDA baseline topic model
The notebook SHALL fit a gensim LDA model on the corpus using spaCy German lemmatization with stopword and non-alphabetic filtering, over a topic count chosen in the 6-10 range with the choice justified (e.g. coherence comparison). It SHALL display the top terms per topic and each document's dominant topic.

#### Scenario: LDA fit and inspection
- **WHEN** the LDA section runs
- **THEN** it prints top terms for every topic and a per-document dominant-topic assignment covering the full corpus

### Requirement: BERTopic model on multilingual embeddings
The notebook SHALL fit a BERTopic model on the raw (non-lemmatized) langtexts using the `paraphrase-multilingual-MiniLM-L12-v2` sentence-transformer, and SHALL report the topic-info table including the outlier topic size.

#### Scenario: BERTopic fit
- **WHEN** the BERTopic section runs
- **THEN** it produces a fitted model whose `get_topic_info()` output is displayed, including topic sizes and representative c-TF-IDF terms per topic

### Requirement: Validation of discovered topics against trade labels
The notebook SHALL evaluate both models against the ground-truth trade labels using a topic-by-label crosstab and at least one alignment score (purity or normalized mutual information) computed for both models, and SHALL visualize the BERTopic topic space (`visualize_topics` or equivalent) and top terms per topic (`visualize_barchart` or equivalent).

#### Scenario: Alignment evaluation
- **WHEN** the validation section runs
- **THEN** it displays a crosstab of discovered topics versus trade labels and prints the alignment score for LDA and for BERTopic on the same corpus

### Requirement: Topic prediction for held-out texts
The notebook SHALL use the fitted BERTopic model to predict topics for held-out texts that were not part of the training corpus: the stored conversation user/assistant messages and the six Baubeschreibung sections used in `nlp-textsummary`. Each held-out text SHALL be shown with its predicted topic and the topic's representative terms, followed by a written plausibility assessment.

#### Scenario: Held-out prediction
- **WHEN** the prediction section runs
- **THEN** every held-out text receives a predicted topic (or the outlier topic) and the notebook prints text excerpt, predicted topic terms, and assignment confidence where available

### Requirement: Model comparison and interpretation
The notebook SHALL close with a discussion section that compares LDA and BERTopic results on this corpus and states which model aligns better with the actual trade categories and why, addressing the course question "why is one performing better than another?".

#### Scenario: Interpretation present
- **WHEN** the notebook is read end-to-end
- **THEN** the final section contains a reasoned comparison referencing the computed alignment scores and concrete topic examples

### Requirement: Reviewable self-contained deliverable
The notebook SHALL live in `nlp-topics/` with a jupytext-paired `.py` source, its own `pyproject.toml` declaring all direct dependencies (including `spacy`, `gensim`, `bertopic`, `sentence-transformers`), a fully executed `.ipynb` with committed outputs, and a rendered HTML export so a reviewer can read results without running anything. `AE.NLP.2.5.README.md` SHALL map the topic-prediction evaluation criterion to this notebook.

#### Scenario: Review without execution
- **WHEN** a reviewer opens the committed HTML export or `.ipynb`
- **THEN** all cells show executed outputs including figures, with no execution required and no missing-output cells
