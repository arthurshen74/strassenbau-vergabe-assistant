"""Pydantic models: registry schema, LLM structured outputs, runtime artifacts.

Three model families:
  1. Registry models  - validate the YAML at load time (the knowledge base).
  2. LLM outputs      - structured outputs for the three LLM call sites.
  3. Runtime artifacts- cost lines with provenance, the EKT, review flags.
The formula INPUT models live in formulas.py next to their functions.
"""
from __future__ import annotations
from enum import StrEnum
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
    hint: Optional[str] = None           # German retrieval query (plan/project/judgment)
    description: Optional[str] = None    # decision rule shown to the LLM and the reviewer
    confirm: bool = False                # assumption: always pause for HITL confirmation


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
REASONING_DESCRIPTION = (
    "2-5 short thinking steps, written FIRST: what the text says -> which "
    "rule/criterion applies -> what you conclude. Cite decisive wording."
)


class ClassificationResult(BaseModel):
    """LLM site 1: classify the LV position into a registered work_type."""
    reasoning: list[str] = Field(default=[], description=REASONING_DESCRIPTION)
    work_type: str = Field(description="One of the offered work_type codes, or 'unknown'")
    confidence: float = Field(ge=0, le=1)
    notes: str = Field(description="1-2 sentences, cite the decisive wording")


class DriverDecision(BaseModel):
    """LLM site 2 (one call per driver): the resolved value + its reasoning for ONE driver."""
    reasoning: list[str] = Field(default=[], description=REASONING_DESCRIPTION)
    value: Union[str, float, int, None] = None
    source_quote: Optional[str] = Field(
        default=None, description="Verbatim snippet the value was read from")
    confidence: float = Field(ge=0, le=1)
    note: Optional[str] = Field(
        default=None, description="Why the value is missing or ambiguous, if it is")


class MethodSelection(BaseModel):
    """LLM site 3: pick a Bauweise for one operation."""
    reasoning: list[str] = Field(default=[], description=REASONING_DESCRIPTION)
    method: str = Field(description="One of the offered method ids, or 'escalate'")
    confidence: float = Field(ge=0, le=1)
    notes: str = Field(description="Which criteria + drivers decided it")


# --------------------------------------------------------- runtime artifacts --
class Kostenart(StrEnum):
    """VHB 223 cost categories; every cost-producing formula maps to exactly one."""
    LOHN = "lohn"
    STOFFE = "stoffe"
    GERAETE = "geraete"
    SONSTIGES = "sonstiges"


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
    labor_h: Optional[float] = None      # crew hours behind a Lohn line (Zeitansatz)
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


class Form223Row(BaseModel):
    """VHB Formblatt 223-style Aufgliederung of one position's EP (ohne USt),
    emitted when the Kalkulator approves the assessment."""
    oz: str
    kurzbezeichnung: str
    menge: float
    mengeneinheit: str
    zeitansatz_h: float                  # labor hours per Mengeneinheit
    lohn_eur: float                      # all costs per Mengeneinheit, ohne USt
    stoffe_eur: float
    geraete_eur: float
    sonstiges_eur: float
