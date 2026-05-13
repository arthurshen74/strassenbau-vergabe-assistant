"""Pydantic schemas for LLM structured outputs in the ingest pipeline.

These are extraction-time shapes — narrower than the application-layer
graph schemas in graph/models.py, which carry ids, timestamps, embeddings,
and other fields the LLM never produces.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ExtractedParagraph(BaseModel):
    page: int = Field(ge=1)
    paragraph: int = Field(ge=1)
    text: str


class ExtractedPage(BaseModel):
    paragraphs: list[ExtractedParagraph]


class TranslatedParagraph(BaseModel):
    translation: str


class SubstantiveStart(BaseModel):
    page: int = Field(ge=1)
    paragraph: int = Field(ge=1)


Classification = Literal[
    "factual", "legal", "rhetorical", "procedural", "evidentiary"
]


class ExtractedAssertion(BaseModel):
    assertion_text: str
    assertion_text_en: str
    classification: Classification
    is_negative: bool


class ExtractedAssertions(BaseModel):
    assertions: list[ExtractedAssertion]
