# Project Overview

Pipeline for producing structured case-preparation artifacts from labor-law case files.

## What This Produces

A Streamlit UI that shows four datasets:

1. **Fact Chronology** — dated events, descriptions, evidence references.
2. **Evidence Index** — each document cross-referenced to the facts it supports or contradicts.
3. **Klageerwiderung Paragraph Analysis** — paragraph classification, substantiation status, and affirmative-version links.
4. **Contradictions List** — categorized contradictions with confidence and source paragraphs.

## Requirements

- Python 3.12.12
- Anthropic API key (set as `ANTHROPIC_API_KEY` in `.env`)
- Poppler installed locally (brew install poppler)

## Setup

```bash
# after you clone the repo. make yourself a .env file.
touch .env
echo "ANTHROPIC_API_KEY=<your_api_key>" >> .env

# docker up your graphdb
docker compose up --build -d

```

## Project Structure

```
.
├── dbdata/                   # Generated artifacts (gitignored)
│   ├── evidence.db           # SQLite store of extracted PDF text
│   ├── candidate_facts.json
│   ├── facts.json
│   ├── classifications.json
│   └── candidate_contradictions.json
├── data/                     # Source documents (gitignored, read-only)
│   ├── anlagen/              # Evidence PDFs
│   ├── klageschrift/
│   ├── klageerwiderung/
│   └── timelines/
├── out/                       # Final outputs (gitignored)
│   └── replik_artifacts.xlsx
├── plans/                     # Schema specs/plans
├── ui/                        # Streamlit review apps
│   ├── facts.py
│   ├── linking.py
│   ├── klage_review.py
│   └── contradictions.py
├── .env                       # Your active .env file with keys/secrets
├── .env.sample                # Sample .env
├── docker-compose.yml         # Docker Compose configuration.
├── README.md
├── requirements.txt           # Python packages.
└── 125.md                     # Class project requirements
```

## Pipeline
