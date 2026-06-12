"""Pydantic models: registry schema, LLM structured outputs, runtime artifacts.

Three model families:
  1. Registry models  - validate the YAML at load time (the knowledge base).
  2. LLM outputs      - structured outputs for the three LLM call sites.
  3. Runtime artifacts- cost lines with provenance, the EKT, review flags.
The formula INPUT models live in formulas.py next to their functions.
"""
from __future__ import annotations
from typing import Literal, Optional, Union
from pydantic import BaseModel, Field


# ---------------------------------------------------------------- registry --
class ParamSpec(BaseModel):
    from_: Literal["drivers", "store", "prior", "const"] = Field(alias="from")
    field: Optional[str] = None          # from: drivers
    call: Optional[str] = None           # from: store -> stores.STORES[call]
    args: list[str] = []                 # names resolved from context/drivers
    args_const: list[str] = []           # literal args
    ref: Optional[str] = None            # from: prior -> earlier out.id
    value: Optional[Union[str, float, int]] = None   # from: const

    model_config = {"populate_by_name": True}


class OutSpec(BaseModel):
    id: str
    einheit: str


class RequirementRow(BaseModel):
    goal: str
    formula: str
    params: dict[str, ParamSpec]
    out: Optional[OutSpec] = None        # rows without `out` produce a cost (EUR)


class MethodDef(BaseModel):
    id: str
    machine_class: str
    criteria: str


class SelectionSpec(BaseModel):
    on: list[str] = []
    consult: list[str] = []


class DriverSpec(BaseModel):
    id: str
    source: str                          # lv_text | plan | project | tool:* | judgment
    einheit: Optional[str] = None
    options: Optional[list[str]] = None  # for judgment drivers


class DerivedDriverSpec(BaseModel):
    id: str
    einheit: str
    formula: str
    params: dict[str, ParamSpec]


class OperationDef(BaseModel):
    id: str
    label: str
    methods: Optional[list[MethodDef]] = None
    selection: Optional[SelectionSpec] = None
    requirements: list[RequirementRow]


class Registry(BaseModel):
    work_type: str
    version: str
    triggers: dict
    drivers: list[DriverSpec]
    derived_drivers: list[DerivedDriverSpec] = []
    operations: list[OperationDef]


# ------------------------------------------------------------- LLM outputs --
class ClassificationResult(BaseModel):
    """LLM site 1: classify the LV position into a registered work_type."""
    work_type: str = Field(description="One of the offered work_type codes, or 'unknown'")
    confidence: float = Field(ge=0, le=1)
    notes: str = Field(description="1-2 sentences, cite the decisive wording")


class DriverValue(BaseModel):
    id: str
    value: Union[str, float, int, None] = None
    einheit: Optional[str] = None
    source_quote: Optional[str] = Field(
        default=None, description="Verbatim snippet the value was read from")
    confidence: float = Field(ge=0, le=1)


class DriverResolution(BaseModel):
    """LLM site 2: extract document-sourced drivers + decide judgment drivers."""
    drivers: list[DriverValue]
    flags: list[str] = Field(default=[], description="Anything missing/ambiguous")


class MethodSelection(BaseModel):
    """LLM site 3: pick a Bauweise for one operation."""
    method: str = Field(description="One of the offered method ids, or 'escalate'")
    confidence: float = Field(ge=0, le=1)
    notes: str = Field(description="Which criteria + drivers decided it")


# --------------------------------------------------------- runtime artifacts --
class ResolvedParam(BaseModel):
    value: object
    source: str                          # e.g. "driver:strip_width_m", "store:bgl_rate(roller_7t)"


class CostLine(BaseModel):
    operation: str
    method: Optional[str]
    goal: str
    formula: str
    params: dict[str, ResolvedParam]
    eur: Optional[float] = None          # None for intermediate rows (hours, tonnage)
    out_id: Optional[str] = None
    out_value: Optional[float] = None
    out_einheit: Optional[str] = None
    note: Optional[str] = None


class OperationResult(BaseModel):
    operation: str
    method: Optional[str]
    method_confidence: Optional[float] = None
    method_notes: Optional[str] = None
    lines: list[CostLine]
    eur_total: float


class ReviewFlag(BaseModel):
    where: str
    kind: Literal["low_confidence", "blocked", "missing_data", "risk"]
    detail: str
