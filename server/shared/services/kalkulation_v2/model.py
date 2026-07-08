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
  * Formel              – a BASE formula: a string expression over DECLARED formal
                          parameters (name + einheit + prose), written once in
                          canonical units and evaluated through a restricted
                          Python AST (the "DSL"). ~16 of them cover the catalog.
  * FormelInstanz       – one application of a base formula: a dict binding of its
                          parameters to source paths (kontext.x, stammdaten.x,
                          baustoff.x, formel.other_instanz, or a literal). The
                          unit converter scales a bound value at the seam.
  * Vorgang.rechnung    – the per-Vorgang set of instantiations: named quantity/
                          curve instanzen plus the cost lines per Kostenart.
  * Kalkulator          – the ONLY compiled part: resolves variables through their
                          cascade (STAMMDATEN/KONSTANTE deterministically; the
                          LLM/HITL steps are filled by the StateGraph before calc).

Every resolved value is a VariablenWert carrying its provenance (quelle) and, for
extracted inputs, confidence + evidence → the EKT stays auditable. Instanz results
are recorded Vorgang-scoped ("V_FRAESEN::arbeitszeit") with the same provenance.

Determinism note: arithmetic is Decimal; the evaluator is pure (no I/O, now(),
random); cycles are detected. Machine binding keeps its two override seams: a bound
machine's Leistungsprofil replaces the Vorgang's leistung instanz (scoped ctx hit),
and its property bag replaces the Stammdaten rate variables (global ctx hit) — the
Stammdaten rates remain the no-machine defaults.
"""

from __future__ import annotations

import ast
import operator
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_FLOOR
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from shared.services.kalkulation_v2 import einheiten


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


class FormelParameter(BaseModel):
    """One declared formal parameter of a base formula: canonical einheit + sourcing prose."""
    model_config = ConfigDict(extra="forbid")

    name: str
    einheit: str | None = None                # canonical unit; None = polymorphic (e.g. "menge")
    beschreibung: str | None = None           # meaning + where to find the value (ontology prose)
    standard: Decimal | None = None           # default when an instanz leaves the parameter unbound


class Formel(BaseModel):
    """A base formula: one DSL expression over its declared parameters, written once in
    canonical units. Applied via FormelInstanz bindings — never by copying the expression."""
    model_config = ConfigDict(extra="forbid")

    name: str
    ausdruck: str                             # the DSL expression over parameter names
    einheit: str | None = None                # unit of the result
    beschreibung: str | None = None           # what it computes and when to use it
    parameter: list[FormelParameter] = Field(default_factory=list)

    def parameter_namen(self) -> set[str]:
        return {p.name for p in self.parameter}

    def parameter_von(self, name: str) -> FormelParameter | None:
        return next((p for p in self.parameter if p.name == name), None)

    def eingaben(self) -> set[str]:
        """Discover referenced names by parsing the AST."""
        baum = ast.parse(self.ausdruck, mode="eval")
        return {n.id for n in ast.walk(baum) if isinstance(n, ast.Name)} - set(_FUNKTIONEN)

    def funktionen(self) -> set[str]:
        """Function names in call position (Call targets) — the DSL functions the formula invokes."""
        baum = ast.parse(self.ausdruck, mode="eval")
        return {
            n.func.id
            for n in ast.walk(baum)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
        }

    def validieren(self) -> list[str]:
        """Dry-check before saving: parseable, closed over the declared signature, and every
        declared parameter used. An unknown *function* (a Call target outside the DSL whitelist)
        gets a distinct message naming the whitelist so the author can express the math with
        existing vocabulary or formulate an engineering request (never invent a function)."""
        try:
            eingaben = self.eingaben()
        except SyntaxError as e:
            return [f"Syntaxfehler: {e}"]
        probleme: list[str] = []
        verfuegbar = ", ".join(sorted(_FUNKTIONEN))
        for fn in sorted(self.funktionen() - set(_FUNKTIONEN)):
            probleme.append(
                f"unbekannte Funktion '{fn}' — keine DSL-Funktion. Verfügbar: {verfuegbar}. "
                "Mit vorhandenem Vokabular ausdrücken oder als Entwicklerauftrag formulieren."
            )
        deklariert = self.parameter_namen()
        for ref in sorted((eingaben - self.funktionen()) - deklariert):
            probleme.append(f"Ausdruck referenziert undeklarierten Parameter: {ref}")
        for unbenutzt in sorted(deklariert - eingaben):
            probleme.append(f"deklarierter Parameter wird im Ausdruck nicht verwendet: {unbenutzt}")
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
    baustoff_code: str
    preis_eur_pro_t: Decimal
    gueltig_ab: date
    gueltig_bis: date | None = None


class Baustoff(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str
    name: str
    rohdichte_t_pro_m3: Decimal
    verdichtungsfaktor: Decimal = Decimal("1.0")
    kategorie: str | None = None
    koernung: str | None = None
    einheit: str = "t"
    basispreis_eur_pro_t: Decimal | None = None      # €/t — bulk/tonnage costing + supplier comparison
    basispreis_eur: Decimal | None = None            # price per `einheit` — the universal material-cost rate


class Baustofflieferant(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str
    name: str
    standort: str | None = None
    breitengrad: Decimal | None = None
    laengengrad: Decimal | None = None
    preise: list[BaustoffPreis] = Field(default_factory=list)

    def preis_fuer(self, baustoff_code: str, stichtag: date) -> Decimal | None:
        for p in self.preise:
            if p.baustoff_code == baustoff_code and p.gueltig_ab <= stichtag and (
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
# Machine catalog (master data) — operation taxonomy + a property-bag fleet.
# All domain data (editable without recompile); only the engine vocabularies
# (AufloesungsMethode, Kostenart) stay compiled.
# --------------------------------------------------------------------------- #
class Betriebskategorie(BaseModel):
    """A grouping of operation modes, e.g. 'fraesen', 'verdichtung'. Editable data."""
    model_config = ConfigDict(extra="forbid")
    code: str
    bezeichnung: str
    beschreibung: str | None = None


class Betriebsart(BaseModel):
    """One operation mode, e.g. 'feinfraesen' under 'fraesen'. Selects a machine's
    productivity profile. Referenced by string code; editable data, no recompile."""
    model_config = ConfigDict(extra="forbid")
    code: str
    bezeichnung: str
    kategorie_code: str                        # FK -> Betriebskategorie.code (validated at load)
    einheit: str | None = None                 # default productivity unit hint: "m2/h" | "m/h"
    beschreibung: str | None = None


class MaschinenWert(BaseModel):
    """One machine property: value (number / text / bool) + unit. Numeric properties
    bound to a cost variable bridge into the calc; text/bool are descriptive/selection."""
    model_config = ConfigDict(extra="forbid")
    wert: bool | Decimal | str
    einheit: str | None = None
    beleg: str | None = None                   # e.g. datasheet reference


class Leistungsprofil(BaseModel):
    """Productivity for one Betriebsart (+ optional profile-specific property overrides,
    e.g. higher wear on a harder operation)."""
    model_config = ConfigDict(extra="forbid")
    betriebsart_code: str                      # FK -> Betriebsart.code
    leistung: Decimal
    einheit: str                               # may differ per profile (m2/h vs m/h)
    eigenschaften: dict[str, MaschinenWert] = Field(default_factory=dict)


class Maschine(BaseModel):
    """A concrete machine that can fill an Ausführungsart slot. The `eigenschaften`
    property bag holds operating cost, fuel, mob/demob and any added spec; the
    `leistungsprofile` give per-Betriebsart productivity."""
    model_config = ConfigDict(extra="forbid")
    code: str
    hersteller: str
    modell: str
    ausfuehrungsart_code: str                  # which slot it fills (FK -> Ausführungsart.code)
    eigenschaften: dict[str, MaschinenWert] = Field(default_factory=dict)
    leistungsprofile: list[Leistungsprofil] = Field(default_factory=list)

    def eigenschaft(self, key: str) -> MaschinenWert | None:
        return self.eigenschaften.get(key)

    def leistung_fuer(self, betriebsart_code: str) -> Leistungsprofil | None:
        return next((p for p in self.leistungsprofile if p.betriebsart_code == betriebsart_code), None)




# --------------------------------------------------------------------------- #
# Catalog hierarchy (Vorgang now references cost variables, not embedded classes)
# --------------------------------------------------------------------------- #
class Ausführungsart(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str
    name: str
    geraetebezug: str | None = None


class FormelInstanz(BaseModel):
    """One application of a base formula: parameters bound to source paths or literals.

    Path grammar: `kontext.<var>` / `stammdaten.<var>` (cascade resolution via Kalkulator),
    `baustoff.<feld>` (the bound Baustoff), `formel.<instanz>` (another instanz of the same
    Vorgang), or a numeric literal. An unbound parameter falls back to its declared default.
    `variable` names the kontext variable this instanz materializes — a booked/extracted
    value for it wins over computing (the t-billed vs m²-billed geometry seam).

    `einheiten` pins a concrete unit onto a POLYMORPHIC formula parameter (einheit None,
    e.g. F_MENGE_ANSATZ.ansatz) so the converter can scale the bound source (kg/m² -> t/m²);
    `ergebnis_einheit` does the same for a polymorphic result consumed by another instanz.
    """
    model_config = ConfigDict(extra="forbid")

    formel: str
    bindung: dict[str, str] = Field(default_factory=dict)
    einheiten: dict[str, str] = Field(default_factory=dict)
    ergebnis_einheit: str | None = None
    variable: str | None = None
    bezeichnung: str | None = None            # display label for Nachweis / EKT lines


class VorgangRechnung(BaseModel):
    """A Vorgang's cost computation: named quantity/curve instanzen plus the cost lines
    per Kostenart (a list — Material may carry several lines). Kostenart order drives the
    Nachweis cost-line order."""
    model_config = ConfigDict(extra="forbid")

    instanzen: dict[str, FormelInstanz] = Field(default_factory=dict)
    kosten: dict[Kostenart, list[FormelInstanz]] = Field(default_factory=dict)


# Einheiten of the Decimal-typed Baustoff fields addressable as `baustoff.<feld>`.
BAUSTOFF_PFAD_EINHEITEN: dict[str, str | None] = {
    "rohdichte_t_pro_m3": "t/m3",
    "verdichtungsfaktor": "-",
    "basispreis_eur_pro_t": "€/t",
    "basispreis_eur": None,
}


class Vorgang(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str
    name: str
    ausfuehrungsart: Ausführungsart | None = None
    # Machine-selection seam: the operation's productivity profile (betriebsart_code);
    # a bound machine overrides the named leistung instanz (scoped) and the Stammdaten
    # rate variables named in kosten_bindung (rate variable -> property-bag key).
    betriebsart_code: str | None = None
    leistung_instanz: str | None = None
    kosten_bindung: dict[str, str] = Field(default_factory=dict)
    rechnung: VorgangRechnung = Field(default_factory=VorgangRechnung)

    def instanz_scope(self, instanz_name: str) -> str:
        return f"{self.code}::{instanz_name}"

    def _wert_fuer(self, pfad: str, ziel_einheit: str | None, kalk: Kalkulator,
                   ctx: Kalkulationskontext, cache: dict[str, Decimal],
                   kette: frozenset[str]) -> Decimal:
        """Resolve one bound source path to a Decimal in the target einheit."""
        praefix, _, rest = pfad.partition(".")
        if praefix in ("kontext", "stammdaten") and rest:
            wert = kalk.resolve(rest, ctx)
            defn = kalk.katalog.get(rest)
            return einheiten.konvertiere(wert, defn.einheit if defn else None, ziel_einheit)
        if praefix == "baustoff" and rest:
            baustoff = ctx.stammdaten.get("baustoff")
            wert = getattr(baustoff, rest, None)
            if not isinstance(wert, Decimal):
                raise ValueError(f"{self.code}: Baustoff-Feld nicht auflösbar: {pfad}")
            return einheiten.konvertiere(wert, BAUSTOFF_PFAD_EINHEITEN.get(rest), ziel_einheit)
        if praefix == "formel" and rest:
            wert = self._instanz_wert(rest, kalk, ctx, cache, kette)
            inst = self.rechnung.instanzen[rest]
            quell_einheit = inst.ergebnis_einheit or kalk.formeln[inst.formel].einheit
            return einheiten.konvertiere(wert, quell_einheit, ziel_einheit)
        try:
            return Decimal(pfad)  # literal — assumed to be in the parameter's einheit
        except InvalidOperation:
            raise ValueError(f"{self.code}: unbekannter Bindungspfad: {pfad!r}") from None

    def _auswerten(self, inst: FormelInstanz, kalk: Kalkulator, ctx: Kalkulationskontext,
                   cache: dict[str, Decimal], kette: frozenset[str]) -> Decimal:
        formel = kalk.formeln[inst.formel]

        def resolver(param_name: str) -> Decimal:
            param = formel.parameter_von(param_name)
            pfad = inst.bindung.get(param_name)
            if pfad is not None:
                ziel_einheit = inst.einheiten.get(param_name) or (
                    param.einheit if param is not None else None
                )
                return self._wert_fuer(pfad, ziel_einheit, kalk, ctx, cache, kette)
            if param is not None and param.standard is not None:
                return param.standard
            raise ValueError(
                f"{self.code}: Parameter '{param_name}' von {inst.formel} ist ungebunden"
            )

        return eval_ausdruck(formel.ausdruck, resolver)

    def _instanz_wert(self, name: str, kalk: Kalkulator, ctx: Kalkulationskontext,
                      cache: dict[str, Decimal], kette: frozenset[str]) -> Decimal:
        """A named quantity/curve instanz: machine override wins, then a booked value for
        the variable it materializes, then compute-and-record (Vorgang-scoped provenance)."""
        if name in cache:
            return cache[name]
        if name in kette:
            raise ValueError(f"{self.code}: Instanz-Zyklus: {' -> '.join([*kette, name])}")
        scoped = self.instanz_scope(name)
        if scoped in ctx.werte:
            cache[name] = ctx.werte[scoped].wert
            return cache[name]
        inst = self.rechnung.instanzen.get(name)
        if inst is None:
            raise KeyError(f"{self.code}: unbekannte Instanz: formel.{name}")
        if inst.variable and inst.variable in ctx.werte:
            cache[name] = ctx.werte[inst.variable].wert
            return cache[name]
        wert = self._auswerten(inst, kalk, ctx, cache, kette | {name})
        ctx.werte[scoped] = VariablenWert(
            name=scoped, wert=wert, quelle=AufloesungsMethode.FORMEL, beleg=inst.formel
        )
        cache[name] = wert
        return wert

    def kalkuliere(self, kalk: Kalkulator, ctx: Kalkulationskontext) -> dict:
        positionen = []
        summe = Decimal("0")
        cache: dict[str, Decimal] = {}
        for kostenart, instanzen in self.rechnung.kosten.items():
            betrag = sum(
                (self._auswerten(i, kalk, ctx, cache, frozenset()) for i in instanzen),
                start=Decimal("0"),
            ).quantize(Decimal("0.01"))
            label = " + ".join(i.bezeichnung or i.formel for i in instanzen)
            positionen.append({"kostenart": kostenart.value, "variable": label,
                               "betrag_eur": betrag, "quelle": AufloesungsMethode.FORMEL.value})
            summe += betrag
        return {"vorgang": self.code, "positionen": positionen,
                "ekt_eur": summe.quantize(Decimal("0.01"))}


class Bauverfahren(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str
    name: str
    vorgaenge: list[Vorgang] = Field(default_factory=list)


class Leistung(BaseModel):
    """The service to be rendered (your 'classification'), e.g. an STLB text.
    A leaf: it does NOT own a Bauverfahren — the calculator selects one to fulfil it."""
    model_config = ConfigDict(extra="forbid")
    code: str
    name: str
    beschreibung: str | None = None
    standard_kennung: str | None = None          # STLB-Bau / FSG key
    einheit: str | None = None
