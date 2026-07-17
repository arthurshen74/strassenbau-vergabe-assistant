from __future__ import annotations

from sqlalchemy import Column, DateTime, Table, Text, func

from shared.db.metadata import metadata

# cache_key is a SHA-256 hex of (spacy model name, model version, render style, sentence
# text); markup is the displacy output (SVG for style=dep). Keying on model+version
# makes a model upgrade a clean miss rather than a stale hit — no separate invalidation.
nlp_render_cache = Table(
    "nlp_render_cache",
    metadata,
    Column("cache_key", Text, primary_key=True),
    Column("style", Text, nullable=False),
    Column("markup", Text, nullable=False),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    ),
)
