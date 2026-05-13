"""Pydantic models for graph nodes.

These models are the application-layer schema enforcement for the
case-preparation knowledge graph. Neo4j Community Edition only enforces
uniqueness constraints natively, so all other invariants from the ontology
(id patterns, enum membership, embedding dimensions, date ordering) are
enforced here, on the write path, before any Cypher executes.

Canonical schema lives in plans/ontology.md.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

EMBEDDING_DIM = 384

DocumentType = Literal[
    "Klageschrift",
    "Klageerweiterung",
    "Klageerwiderung",
    "Replik",
    "Schriftsatz",
    "Beschluss",
    "Protokoll",
    "Anlage",
]

FilingParty = Literal["plaintiff", "defendant", "court"]

Classification = Literal[
    "factual", "legal", "rhetorical", "procedural", "evidentiary"
]
_CLASSIFICATION_VALUES: frozenset[str] = frozenset(Classification.__args__)  # type: ignore[attr-defined]

TemporalScope = Literal["specific_date", "period", "undated"]

SubstantiationStatus = Literal["substantiated", "unsubstantiated", "partial"]


_PARA_ID_RE = re.compile(r"^(?P<doc>.+)_p(?P<page>\d+)_para(?P<para>\d+)$")
_ASSERTION_ID_RE = re.compile(r"^(?P<para>.+)_assertion_(?P<n>\d+)$")


class Document(BaseModel):
    """A Schriftsatz (legal filing) or source evidence document."""

    model_config = ConfigDict(extra="forbid")

    id: str
    document_type: DocumentType
    filing_date: date
    filing_party: FilingParty
    aktenzeichen: str

    author_firm: str | None = None
    total_pages: int | None = Field(default=None, ge=1)
    source_file: str | None = None
    ingested_at: datetime | None = None

    @classmethod
    def build_id(cls, document_type: str, filing_date: date) -> str:
        return f"{document_type.lower()}_{filing_date.strftime('%Y_%m_%d')}"

    @model_validator(mode="after")
    def _check_id_matches_pattern(self) -> Document:
        expected = self.build_id(self.document_type, self.filing_date)
        if self.id != expected:
            raise ValueError(
                f"Document.id {self.id!r} does not match required pattern "
                f"{{document_type_lower}}_{{yyyy_mm_dd}}; expected {expected!r}"
            )
        return self

    @model_validator(mode="after")
    def _check_filing_before_ingest(self) -> Document:
        if self.ingested_at is not None and self.filing_date > self.ingested_at.date():
            raise ValueError(
                f"filing_date {self.filing_date} must be on or before "
                f"ingested_at {self.ingested_at.date()}"
            )
        return self


class Paragraph(BaseModel):
    """A numbered paragraph within a Schriftsatz."""

    model_config = ConfigDict(extra="forbid")

    id: str
    page: int = Field(ge=1)
    paragraph: int = Field(ge=1)
    text_de: str

    text_en: str | None = None
    position: int | None = Field(default=None, ge=1)
    substantiated: bool | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    embedding: list[float] | None = None

    @classmethod
    def build_id(cls, document_id: str, page: int, paragraph: int) -> str:
        return f"{document_id}_p{page}_para{paragraph}"

    @model_validator(mode="after")
    def _check_id_matches_pattern(self) -> Paragraph:
        m = _PARA_ID_RE.match(self.id)
        if m is None:
            raise ValueError(
                f"Paragraph.id {self.id!r} does not match pattern "
                f"{{document_id}}_p{{page}}_para{{paragraph}}"
            )
        if int(m["page"]) != self.page or int(m["para"]) != self.paragraph:
            raise ValueError(
                f"Paragraph.id {self.id!r} disagrees with "
                f"(page={self.page}, paragraph={self.paragraph})"
            )
        return self

    @field_validator("embedding")
    @classmethod
    def _check_embedding_dim(cls, v: list[float] | None) -> list[float] | None:
        if v is not None and len(v) != EMBEDDING_DIM:
            raise ValueError(
                f"embedding must have dimension {EMBEDDING_DIM}, got {len(v)}"
            )
        return v


class Assertion(BaseModel):
    """An atomic claim extracted from a Paragraph (factual, legal, evidentiary, …)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    assertion_text: str

    assertion_text_en: str | None = None
    classification: str | None = None
    temporal_scope: TemporalScope | None = None
    temporal_value: date | str | None = None
    is_negative: bool | None = None
    substantiation_status: SubstantiationStatus | None = None
    embedding: list[float] | None = None
    extracted_at: datetime | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)

    @classmethod
    def build_id(cls, paragraph_id: str, n: int) -> str:
        if n < 1:
            raise ValueError("assertion index n must be >= 1")
        return f"{paragraph_id}_assertion_{n}"

    @model_validator(mode="after")
    def _check_id_matches_pattern(self) -> Assertion:
        m = _ASSERTION_ID_RE.match(self.id)
        if m is None or int(m["n"]) < 1:
            raise ValueError(
                f"Assertion.id {self.id!r} does not match pattern "
                f"{{paragraph_id}}_assertion_{{n}} (n >= 1)"
            )
        return self

    @field_validator("classification")
    @classmethod
    def _check_classification_values(cls, v: str | None) -> str | None:
        if v is None:
            return v
        tokens = [t.strip() for t in v.split(";")]
        if not tokens or any(not t for t in tokens):
            raise ValueError("classification has empty tokens")
        bad = [t for t in tokens if t not in _CLASSIFICATION_VALUES]
        if bad:
            raise ValueError(
                f"classification tokens not allowed: {bad}; "
                f"allowed={sorted(_CLASSIFICATION_VALUES)}"
            )
        return v

    @field_validator("embedding")
    @classmethod
    def _check_embedding_dim(cls, v: list[float] | None) -> list[float] | None:
        if v is not None and len(v) != EMBEDDING_DIM:
            raise ValueError(
                f"embedding must have dimension {EMBEDDING_DIM}, got {len(v)}"
            )
        return v
