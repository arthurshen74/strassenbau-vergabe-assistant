"""
Baukalkulation v2 – metadata-driven (Pydantic v2)
=================================================

The shift from v1: a calculator must add context variables and edit formulas in
a UI WITHOUT a recompile. So neither the context nor the formulas can be Python
classes/methods any more. They become *data*:

  * VariableDefinition  – a context variable described as data: name, einheit,
                          datatype, and an ORDERED resolution cascade. Each
                          resolution step can carry an LLM prompt. The cascade
                          encodes your StateGraph order directly:
                              [LANGTEXT(prompt), RAG(prompt), HITL]
  * Formel              – a calculation written as a string expression, evaluated
                          through a restricted Python AST (the "DSL"). Editable
                          as text; referenced inputs are discovered by parsing.
  * Kalkulator          – the ONLY compiled part: resolves variables (deterministically
                          for FORMEL/STAMMDATEN/KONSTANTE; the LLM/HITL steps are
                          filled by the StateGraph before calc) and evaluates formulas.

Every resolved value is a VariablenWert carrying its provenance (quelle) and, for
extracted inputs, confidence + evidence → the EKT stays auditable.

Determinism note: arithmetic is Decimal; the evaluator is pure (no I/O, now(),
random); cycles are detected. The price of runtime-editable formulas is that
correctness moves from compile-time to runtime — see `Formel.validieren` and the
note about formula versioning at the bottom.
"""

from __future__ import annotations

import ast
import operator
from datetime import date
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


def D(v: str | int | float) -> Decimal:
    return Decimal(str(v))


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #
class Datentyp(str, Enum):
    DEZIMAL = "dezimal"
    GANZZAHL = "ganzzahl"
    TEXT = "text"
    BOOL = "bool"


class AufloesungsMethode(str, Enum):
    LANGTEXT = "langtext"        # extract from LV Langtext + Hinweise (LLM)
    RAG = "rag"                  # query the RAG corpus (LLM)
    HITL = "hitl"                # ask a human
    STAMMDATEN = "stammdaten"    # look up a master-data field
    FORMEL = "formel"            # compute from other variables
    KONSTANTE = "konstante"      # a fixed rate / value


class Kostenart(str, Enum):
    MATERIAL = "Material"
    MASCHINE = "Maschine"
    ANTRANSPORT = "Antransport"
    ABTRANSPORT = "Abtransport"
    ENTSORGUNG = "Entsorgung"
    LOHN = "Lohn"


# --------------------------------------------------------------------------- #
# Variable catalog (managed, runtime-editable)
# --------------------------------------------------------------------------- #
class AufloesungsSchritt(BaseModel):
    """One step in a variable's resolution cascade."""
    model_config = ConfigDict(extra="forbid")

    methode: AufloesungsMethode
    prompt: str | None = None                 # LLM instruction for LANGTEXT / RAG
    konfidenz_schwelle: Decimal | None = None  # min confidence to accept this step
    stammdaten_pfad: str | None = None        # for STAMMDATEN, e.g. "baustoff.rohdichte_t_pro_m3"
    formel_name: str | None = None            # for FORMEL (defaults to the variable name)
    konstante: Decimal | None = None          # for KONSTANTE


class VariableDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str                                 # identifier used inside formulas
    bezeichnung: str
    beschreibung: str | None = None
    einheit: str | None = None
    datentyp: Datentyp = Datentyp.DEZIMAL
    # General semantic context about this variable, injected into the RAG query.
    llm_kontext: str | None = None
    # Ordered cascade: tried top to bottom until one yields an accepted value.
    aufloesung: list[AufloesungsSchritt] = Field(default_factory=list)


class Formel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    ergebnis_variable: str                    # which variable this formula produces
    ausdruck: str                             # the DSL expression
    einheit: str | None = None

    def eingaben(self) -> set[str]:
        """Discover referenced variable names by parsing the AST."""
        baum = ast.parse(self.ausdruck, mode="eval")
        return {n.id for n in ast.walk(baum) if isinstance(n, ast.Name)} - set(_FUNKTIONEN)

    def validieren(self, bekannte_variablen: set[str]) -> list[str]:
        """Dry-check before saving: parseable + every referenced name is known."""
        probleme: list[str] = []
        try:
            self.eingaben()
        except SyntaxError as e:
            return [f"Syntaxfehler: {e}"]
        for ref in self.eingaben():
            if ref not in bekannte_variablen:
                probleme.append(f"unbekannte Variable referenziert: {ref}")
        return probleme


# --------------------------------------------------------------------------- #
# Resolved values (the instance context bag) – carries provenance
# --------------------------------------------------------------------------- #
class VariablenWert(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    wert: Decimal
    quelle: AufloesungsMethode
    konfidenz: Decimal | None = None
    beleg: str | None = None                  # evidence snippet / master-data path


# --------------------------------------------------------------------------- #
# Master data (unchanged in spirit from v1)
# --------------------------------------------------------------------------- #
class BaustoffPreis(BaseModel):
    model_config = ConfigDict(extra="forbid")
    baustoff_id: UUID
    preis_eur_pro_t: Decimal
    gueltig_ab: date
    gueltig_bis: date | None = None


class Baustoff(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID = Field(default_factory=uuid4)
    code: str
    name: str
    rohdichte_t_pro_m3: Decimal
    verdichtungsfaktor: Decimal = Decimal("1.0")
    kategorie: str | None = None
    koernung: str | None = None
    einheit: str = "t"
    basispreis_eur_pro_t: Decimal | None = None


class Baustofflieferant(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID = Field(default_factory=uuid4)
    code: str
    name: str
    standort: str | None = None
    breitengrad: Decimal | None = None
    laengengrad: Decimal | None = None
    preise: list[BaustoffPreis] = Field(default_factory=list)

    def preis_fuer(self, baustoff_id: UUID, stichtag: date) -> Decimal | None:
        for p in self.preise:
            if p.baustoff_id == baustoff_id and p.gueltig_ab <= stichtag and (
                p.gueltig_bis is None or stichtag <= p.gueltig_bis
            ):
                return p.preis_eur_pro_t
        return None


# --------------------------------------------------------------------------- #
# Calculation context (the bag) + catalogs
# --------------------------------------------------------------------------- #
class Kalkulationskontext(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    werte: dict[str, VariablenWert] = Field(default_factory=dict)   # StateGraph-filled + computed
    stammdaten: dict[str, object] = Field(default_factory=dict)     # e.g. {"baustoff": <Baustoff>}
    stichtag: date


# --------------------------------------------------------------------------- #
# AST formula evaluator (the "DSL") – restricted, Decimal, deterministic
# --------------------------------------------------------------------------- #
_BINOPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
           ast.Div: operator.truediv, ast.Mod: operator.mod}
_CMP = {ast.Lt: operator.lt, ast.LtE: operator.le, ast.Gt: operator.gt,
        ast.GtE: operator.ge, ast.Eq: operator.eq, ast.NotEq: operator.ne}
_FUNKTIONEN = {
    "abs": abs, "min": min, "max": max,
    "round": lambda x, n=0: Decimal(x).quantize(Decimal(1).scaleb(-int(n))),
    "ceil": lambda x: Decimal(x).to_integral_value(rounding=ROUND_CEILING),
    "floor": lambda x: Decimal(x).to_integral_value(rounding=ROUND_FLOOR),
}


def eval_ausdruck(ausdruck: str, resolver) -> Decimal:
    """Evaluate a DSL expression. `resolver(name)` returns a Decimal for a variable."""
    baum = ast.parse(ausdruck, mode="eval")

    def _ev(node):
        if isinstance(node, ast.Expression):
            return _ev(node.body)
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool):
                return node.value
            if isinstance(node.value, (int, float)):
                return Decimal(str(node.value))
            raise ValueError(f"unzulässige Konstante: {node.value!r}")
        if isinstance(node, ast.Name):
            return resolver(node.id)
        if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
            left, right = _ev(node.left), _ev(node.right)
            return _BINOPS[type(node.op)](left, right)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Pow):
            return _ev(node.left) ** int(_ev(node.right))
        if isinstance(node, ast.UnaryOp):
            val = _ev(node.operand)
            return -val if isinstance(node.op, ast.USub) else +val
        if isinstance(node, ast.Compare) and len(node.ops) == 1:
            return _CMP[type(node.ops[0])](_ev(node.left), _ev(node.comparators[0]))
        if isinstance(node, ast.BoolOp):
            vals = [_ev(v) for v in node.values]
            return all(vals) if isinstance(node.op, ast.And) else any(vals)
        if isinstance(node, ast.IfExp):
            return _ev(node.body) if _ev(node.test) else _ev(node.orelse)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            return _FUNKTIONEN[node.func.id](*[_ev(a) for a in node.args])
        raise ValueError(f"unzulässiger Ausdruck: {ast.dump(node)}")

    return _ev(baum) # type: ignore


# --------------------------------------------------------------------------- #
# Kalkulator – resolves variables and evaluates formulas
# --------------------------------------------------------------------------- #
class Kalkulator:
    def __init__(self, katalog: dict[str, VariableDefinition], formeln: dict[str, Formel]):
        self.katalog = katalog        # variable name -> definition
        self.formeln = formeln        # formula name -> Formel

    def resolve(self, name: str, ctx: Kalkulationskontext,
                memo: dict[str, Decimal] | None = None,
                pfad: frozenset[str] = frozenset()) -> Decimal:
        memo = memo if memo is not None else {}
        if name in memo:
            return memo[name]
        if name in pfad:
            raise ValueError(f"Zyklus erkannt: {' -> '.join([*pfad, name])}")
        # 1) already resolved (StateGraph filled it from Langtext/RAG/HITL, or a prior compute)
        if name in ctx.werte:
            memo[name] = ctx.werte[name].wert
            return memo[name]
        defn = self.katalog.get(name)
        if defn is None:
            raise KeyError(f"unbekannte Variable: {name}")
        for schritt in defn.aufloesung:
            m = schritt.methode
            if m == AufloesungsMethode.FORMEL:
                formel = self.formeln[schritt.formel_name or name]
                wert = eval_ausdruck(
                    formel.ausdruck,
                    lambda n: self.resolve(n, ctx, memo, pfad | {name}),
                )
                ctx.werte[name] = VariablenWert(name=name, wert=wert, quelle=m)
                memo[name] = wert
                return wert
            if m == AufloesungsMethode.STAMMDATEN:
                wert = self._stammdaten(schritt.stammdaten_pfad, ctx)
                if wert is not None:
                    ctx.werte[name] = VariablenWert(name=name, wert=wert, quelle=m,
                                                    beleg=schritt.stammdaten_pfad)
                    memo[name] = wert
                    return wert
            if m == AufloesungsMethode.KONSTANTE and schritt.konstante is not None:
                ctx.werte[name] = VariablenWert(name=name, wert=schritt.konstante, quelle=m)
                memo[name] = schritt.konstante
                return schritt.konstante
            # LANGTEXT / RAG / HITL are filled by the StateGraph BEFORE calc.
            # Reaching them here means the agent has no value yet → HITL.
        raise ValueError(f"'{name}' nicht auflösbar → HITL (LV Langtext/Hinweise, dann RAG, dann Mensch)")

    @staticmethod
    def _stammdaten(pfad: str | None, ctx: Kalkulationskontext) -> Decimal | None:
        if not pfad:
            return None
        wurzel, *rest = pfad.split(".")
        obj = ctx.stammdaten.get(wurzel)
        for attr in rest:
            obj = getattr(obj, attr, None)
        return obj if isinstance(obj, Decimal) else None


# --------------------------------------------------------------------------- #
# Catalog hierarchy (Vorgang now references cost variables, not embedded classes)
# --------------------------------------------------------------------------- #
class Ausführungsart(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID = Field(default_factory=uuid4)
    code: str
    name: str
    geraetebezug: str | None = None


class Vorgang(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID = Field(default_factory=uuid4)
    code: str
    name: str
    ausfuehrungsart: Ausführungsart | None = None
    # Kostenart -> name of the variable that yields that cost line
    kostenvariablen: dict[Kostenart, str] = Field(default_factory=dict)

    def kalkuliere(self, kalk: Kalkulator, ctx: Kalkulationskontext) -> dict:
        positionen = []
        summe = Decimal("0")
        for kostenart, varname in self.kostenvariablen.items():
            betrag = kalk.resolve(varname, ctx).quantize(Decimal("0.01"))
            quelle = ctx.werte[varname].quelle.value
            positionen.append({"kostenart": kostenart.value, "variable": varname,
                               "betrag_eur": betrag, "quelle": quelle})
            summe += betrag
        return {"vorgang": self.code, "positionen": positionen,
                "ekt_eur": summe.quantize(Decimal("0.01"))}


class Bauverfahren(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID = Field(default_factory=uuid4)
    code: str
    name: str
    vorgaenge: list[Vorgang] = Field(default_factory=list)


class Leistung(BaseModel):
    """The service to be rendered (your 'classification'), e.g. an STLB text.
    A leaf: it does NOT own a Bauverfahren — the calculator selects one to fulfil it."""
    model_config = ConfigDict(extra="forbid")
    id: UUID = Field(default_factory=uuid4)
    code: str
    name: str
    beschreibung: str | None = None
    standard_kennung: str | None = None          # STLB-Bau / FSG key
    einheit: str | None = None
