# Lohnkalkulation für öffentliche Bauvergaben (DE)
### Rules & architecture spec for labor-cost calculation in German public-procurement construction projects

**Status:** working spec · **Audience:** (a) a software engineer who needs to *understand* the domain, (b) a Claude Code agent that needs to *build* the modules and data structures.

> This document describes **how the hourly labor cost (Mittellohn / Kalkulationslohn) is built up**, which **legal floors** constrain it in a *public* tender, and **how to resolve which floors apply** for a given project. It deliberately separates the *deterministic, numeric* logic (everything here) from any LLM reasoning (out of scope — see §10).

---

## 0. Mental model in one paragraph

A construction labor rate is built in **layers**: you start from the **tariff wage** of each worker group, **floor each group** against the highest applicable statutory/contractual minimum, **average the crew** into a *Mittellohn A*, then **load** it with worker-paid extras (*Soziallöhne* → *Mittellohn AS*) and employer social costs (*Lohnzusatzkosten* → *Mittellohn ASL*). In a **public** tender there is an extra overlay: the bidder must commit to **Tariftreue**, the rate must respect a **Land-specific Vergabemindestlohn** floor, temp workers need **Entgeltgleichheit**, and **tariff increases over the execution period** must be priced in. Which floors apply is decided by the **place of execution** and the **type of contracting authority** — *not* by the contractor's registered seat.

---

## 1. Scope

**In scope**
- Build-up of the calculable hourly wage: `Tariflohn → Mittellohn A → AS → ASL`.
- The stacked **wage floors** and the `max()` rule that selects the binding one.
- **Jurisdiction resolution** (which Vergabegesetz / which Vergabemindestlohn / which Tarifzone).
- Public-procurement obligations that touch the number: Tariftreue, Vergabemindestlohn, Entgeltgleichheit, Tarifgleitung over the Laufzeit.

**Out of scope (separate modules)**
- Material cost (e.g. EBV / Ersatzbaustoffe — see the separate material-cost spec).
- Equipment (Geräte), subcontractor (Nachunternehmer) pricing.
- Markups above the labor cost: Baustellengemeinkosten (BGK), Allgemeine Geschäftskosten (AGK), Wagnis & Gewinn — these sit *above* `Mittellohn ASL` in the Angebotskalkulation.
- Above-/below-threshold *procedure* law (GWB/VgV/VOB-A vs. UVgO) beyond what is needed to pick the right floor set.

---

## 2. Legal framework & connecting factors

Two layers of law touch the wage. **Federal/EU procurement law** (GWB, VgV, VOB/A above the EU thresholds; UVgO below) governs the *procedure* and is uniform nationwide. **Land-specific Tariftreue-/Vergabegesetze** add the **Tariftreue commitment** and a **Vergabemindestlohn** on top. The labor floor and the Eigenerklärung come from this Land layer.

### 2.1 Connecting factors (the rule that decides "which Land's rules")

| Question | Connecting factor (key) | Notes |
|---|---|---|
| Which **Vergabegesetz / Tariftreue regime / Vergabemindestlohn**? | **Type of Auftraggeber** + **Land of the place of execution** | A *Land/Kommune* authority procuring → that Land's Vergabegesetz. A *federal (Bund)* authority → **no** Land-Tariftreuegesetz applies, only the federal/EU layer. |
| Which **wage tariff** (Tariflohn body)? | **Tarifzone of the place of execution** (Ost / West / Berlin) | Follows `am Ort der Ausführung`, reinforced independently by **AEntG** (place-of-work principle). |
| Does the **contractor's Sitz** matter? | **No** | A Thüringen-seated contractor working in Sachsen-Anhalt owes SA's Tariftreue layer and the place-of-execution tariff. The seat is irrelevant. |

> **Worked consequence:** Thüringen contractor, project in Sachsen-Anhalt → **SA's** Vergabemindestlohn floor + **SA's** Eigenerklärung apply; the tariff body is **Ost** (same as Thüringen would be), so the base Tariflohn doesn't move — only the floor and the paperwork do.

### 2.2 The relevant instruments

- **TVergG / Landesvergabegesetz** (e.g. *TVergG LSA* for Sachsen-Anhalt, *ThürVgG* for Thüringen): defines the Tariftreue obligation and the Vergabemindestlohn. **Land-specific, versioned by date.**
- **Tarifverträge** (collective agreements):
  - *TV Lohn/Ost* and *TV Gehalt/Ost* — wage/salary tables for the Bauhauptgewerbe in the Beitrittsgebiet (ex-GDR, excl. Berlin).
  - *BRTV Baugewerbe* (Bundesrahmentarifvertrag) — framework: Bauzuschlag, working time, Auslösung, etc.
  - Rahmentarifvertrag for Angestellte/Poliere.
- **AEntG** (Arbeitnehmer-Entsendegesetz): makes the *allgemeinverbindlichen* construction tariffs (incl. the **Branchen-Mindestlohn Bau**) binding by **place of work**, independent of employer seat.
- **MiLoG** (Mindestlohngesetz): the general statutory minimum wage — an absolute floor under everything.
- **AÜG** (Arbeitnehmerüberlassungsgesetz): basis for the **Entgeltgleichheit** requirement for Leiharbeitnehmer.

---

## 3. The floor stack (the `max()` rule)

For **each worker group**, the binding **productive hourly wage** is the **maximum** of all applicable minimums. Flooring happens at the **per-group Grundstundenlohn level** — *before* averaging and *before* loading supplements.

```
effective_wage(group, date, ctx) = max(
    tariff_wage(group, zone, date),          # the group's own tariff rate
    vergabemindestlohn(land, date, ctx),     # Land procurement floor (only in public tenders)
    branchen_mindestlohn_bau(zone, level, date),  # AEntG Bau minimum (place-of-work)
    milog(date)                              # general statutory minimum
)
```

Key precisions:
- The Vergabemindestlohn is a **floor, not a rate**: where the tariff wage already meets/exceeds it, the **tariff wage stays**; only groups *below* it get lifted. (Empirically this typically lifts only the **lowest** Lohngruppe, e.g. LG1.) So flooring is **group-wise**, not a blanket replacement.
- The Branchen-Mindestlohn Bau is itself **zoned/levelled** (historically ML1 vs ML2, with level/zone differences). Model it as a table, not a scalar.
- All four inputs are **date-versioned**. The selected `date` is the **execution date**, not the bid date (see §4 escalation).

---

## 4. Mittellohn build-up (A → AS → ASL)

This is the standard German Kalkulation labor build-up. **Letter conventions vary by textbook** (Drees/Paul, KLR-Bau, etc.); treat the *composition of each layer as configuration*, not hard-coded.

| Layer | Symbol | = previous + | Typical contents |
|---|---|---|---|
| Productive tariff wage | **ML A** | (base) | Crew-weighted average of `effective_wage(group)` **incl. Bauzuschlag** and lohngebundene Zulagen |
| + worker-paid extras | **ML AS** | Soziallöhne | Auslösung/Verpflegungszuschuss, Fahrtkostenabgeltung, vermögenswirksame Leistungen, etc. (paid *to* the worker, not part of the Stundenlohn) |
| + employer social costs | **ML ASL** | Lohnzusatzkosten | Employer SV share (KV/RV/AV/PV), U1/U2 & Insolvenzgeldumlage, **BG Bau**, **SOKA-Bau** (ULAK/ZVK/Berufsbildung), Winterbeschäftigungs-Umlage, Lohnfortzahlung |

- **ML ASL is the Kalkulationsmittellohn** — the per-hour labor cost that multiplies productive hours. Everything above it (BGK, AGK, W&G) is a later markup, out of scope here.
- The **Lohnzusatzkostensatz** in the Bauhauptgewerbe is large (commonly **~80–95 %** on ML A/AS) precisely because of SOKA-Bau + high social charges. **Do not hard-code** — make it a versioned, sourced parameter set.

### 4.1 Crew weighting (Kolonnenbesetzung)

`ML A` is the **headcount-weighted** average of the group rates:

```
ML_A = Σ_g ( count_g * effective_wage(g) ) / Σ_g count_g
```

The crew mix (e.g. Werker / Fachwerker / Spezialfacharbeiter / Vorarbeiter / Polier) is **per-Position or per-Gewerk input**, not a global constant.

---

## 5. Deterministic calculation pipeline

Pure numeric/lookup — no LLM. Ordered so floors apply before aggregation:

1. **Resolve jurisdiction** from `ProjectContext` → `{ vergabegesetz?, vergabemindestlohn_ruleset?, requires_eigenerklaerung, tarifzone }`. (§2.1)
2. **Resolve tariff version**: pick the `Tarifvertrag` table valid for `zone` at the relevant `date`.
3. **For each WageGroup in the crew**: compute `effective_wage` via the `max()` floor stack. (§3)
4. **Weight** into `ML A`. (§4.1)
5. **Add Soziallöhne** → `ML AS` (from `SozialzulagenProfile`).
6. **Apply Lohnzusatzkostensatz** → `ML ASL` (from `LohnzusatzkostenProfile`).
7. **Escalation**: if the execution period spans known/expected tariff steps, repeat 2–6 per period segment and time-weight, or apply a documented Tarifgleit-/Preisgleitklausel. Output a per-period schedule, not a single frozen number.
8. **Emit** `MittellohnResult` with full provenance (which tariff version, which floor bound each group, which profiles).

> **Ordering matters:** flooring (step 3) is on the **Grundstundenlohn**, *before* weighting and loading. Flooring the loaded `ML ASL` instead would be wrong.

---

## 6. Data structures

Shown as Python-style typed schemas (maps cleanly to C#/TS records). All money is integer **cents**; all rates are decimals; everything carrying a value is **date-versioned**.

```python
from dataclasses import dataclass
from datetime import date
from enum import Enum

class Tarifzone(Enum):
    OST = "ost"
    WEST = "west"
    BERLIN = "berlin"

class AuftraggeberTyp(Enum):
    BUND = "bund"
    LAND = "land"
    KOMMUNE = "kommune"
    SONSTIGE_OEFFENTLICH = "sonstige"

# ---- versioned value base -------------------------------------------------
@dataclass(frozen=True)
class Validity:
    valid_from: date
    valid_to: date | None      # None = open-ended / until kündbar

# ---- tariff side ----------------------------------------------------------
@dataclass(frozen=True)
class WageGroup:
    id: str                    # e.g. "LG1", "LG4", "POLIER"
    label: str

@dataclass(frozen=True)
class TariffRate:
    group_id: str
    hourly_cents: int          # Tarifgrundstundenlohn
    includes_bauzuschlag: bool # document the convention explicitly

@dataclass(frozen=True)
class Tarifvertrag:
    id: str                    # e.g. "TV_LOHN_OST_2024"
    zone: Tarifzone
    validity: Validity
    rates: list[TariffRate]
    bauzuschlag_pct: float | None   # if not already in rates

# ---- the floors -----------------------------------------------------------
@dataclass(frozen=True)
class Vergabemindestlohn:
    land: str                  # ISO-ish: "ST" (Sachsen-Anhalt), "TH" (Thüringen)
    hourly_cents: int
    validity: Validity
    source_url: str            # official Handlungsanleitung / Tarifregister

@dataclass(frozen=True)
class BranchenMindestlohnBau:   # AEntG, place-of-work
    zone: Tarifzone
    level: str                 # "ML1" | "ML2" ...
    hourly_cents: int
    validity: Validity

@dataclass(frozen=True)
class MiLoG:
    hourly_cents: int
    validity: Validity

# ---- loading profiles -----------------------------------------------------
@dataclass(frozen=True)
class SozialzulagenProfile:
    # worker-paid extras → ML AS. Express as per-hour cents or % as appropriate.
    components: dict[str, int]      # e.g. {"auslösung": 0, "fahrgeld": 0, "vwl": ...}

@dataclass(frozen=True)
class LohnzusatzkostenProfile:
    # employer social costs → ML ASL. Each a rate on the chosen base.
    components: dict[str, float]    # e.g. {"sv_ag": .20, "soka_bau": .., "bg_bau": ..}
    validity: Validity
    @property
    def total_rate(self) -> float:
        return sum(self.components.values())

# ---- crew & project -------------------------------------------------------
@dataclass(frozen=True)
class CrewMember:
    group_id: str
    count: float               # allow fractional (e.g. shared Polier)

@dataclass(frozen=True)
class CrewComposition:
    members: list[CrewMember]

@dataclass(frozen=True)
class ExecutionPeriod:
    start: date
    end: date

@dataclass(frozen=True)
class ProjectContext:
    ausfuehrungsort_land: str       # decides Vergabegesetz + Vergabemindestlohn
    tarifzone: Tarifzone            # decides tariff body
    auftraggeber_typ: AuftraggeberTyp
    is_public: bool
    period: ExecutionPeriod
    # derived: above/below EU threshold, WSG flags, etc.

# ---- result ---------------------------------------------------------------
@dataclass(frozen=True)
class GroupWageResolution:
    group_id: str
    effective_cents: int
    binding_floor: str          # "tarif" | "vergabemindestlohn" | "bau_ml" | "milog"

@dataclass(frozen=True)
class MittellohnResult:
    ml_a_cents: int
    ml_as_cents: int
    ml_asl_cents: int
    per_group: list[GroupWageResolution]
    tarifvertrag_id: str
    lohnzusatz_rate: float
    period: ExecutionPeriod
    provenance: dict            # every source/version used
```

---

## 7. Module breakdown (for the Claude Code agent)

```
lohn/
├── jurisdiction.py     # resolve_jurisdiction(ctx) -> JurisdictionRuleset
│                       #   (which Vergabegesetz, which Vergabemindestlohn set,
│                       #    requires_eigenerklaerung, tarifzone)
├── floors.py           # effective_wage(group, date, ctx) -> GroupWageResolution
│                       #   implements the max() stack; returns binding_floor
├── tariff.py           # tariff lookup by (zone, date); Bauzuschlag handling
├── mittellohn.py       # compute_mittellohn(crew, ctx, profiles) -> MittellohnResult
│                       #   steps 2–6 of the pipeline, group-wise flooring first
├── escalation.py       # segment the execution period across tariff steps,
│                       #   time-weight or apply a Gleitklausel
├── profiles.py         # load Sozialzulagen / Lohnzusatzkosten profiles (versioned)
├── data/               # the versioned reference data (see §9) — NOT code
│   ├── tarifvertraege/*.json
│   ├── vergabemindestlohn/*.json
│   ├── bau_mindestlohn/*.json
│   └── milog.json
└── tests/              # golden cases incl. the cross-border (TH→ST) scenario
```

**Boundaries to keep clean**
- `jurisdiction.py` is the *only* place that maps `(land, auftraggeber_typ)` → ruleset. Everything else consumes its output.
- `floors.py` never reaches for "current" values; it takes a `date` and looks up versioned rows. No `datetime.now()` inside the calc.
- Reference figures live in `data/` as versioned rows, **never as literals in code** (see §9).

---

## 8. Worked example (illustrative — numbers are placeholders)

> ⚠️ Figures below are **structure placeholders**, not real rates. Populate from official sources (§9) before use.

Project: road job, **Ausführungsort = Sachsen-Anhalt**, **Land/Kommune** Auftraggeber, public, exec 2026. Contractor seat: Thüringen (irrelevant).

1. Jurisdiction → `vergabegesetz=TVergG_LSA`, `vergabemindestlohn=VML_ST_2026`, `requires_eigenerklaerung=True`, `tarifzone=OST`.
2. Tariff → `TV_LOHN_OST_2024` (Ost — same body Thüringen would use).
3. Per group (productive €/h, placeholders):

| Group | Tariff | VML floor | Bau-ML | MiLoG | **effective** | bound by |
|---|---|---|---|---|---|---|
| LG1 | 14.00 | 15.50 | 13.50 | 12.82 | **15.50** | vergabemindestlohn |
| LG4 | 19.00 | 15.50 | 13.50 | 12.82 | **19.00** | tarif |
| Polier | 26.00 | 15.50 | – | 12.82 | **26.00** | tarif |

4. Crew {LG1×3, LG4×2, Polier×1} → `ML A = (3·15.50 + 2·19.00 + 26.00)/6 = 18.58 €/h`.
5. + Soziallöhne (e.g. +0.90) → `ML AS = 19.48`.
6. × (1 + 0.88 Lohnzusatz) → `ML ASL ≈ 36.62 €/h` = Kalkulationsmittellohn.
7. Escalation: if a tariff step lands mid-2026, segment the period and time-weight.

Note how the **only** procurement-driven change vs. a private Thüringen job is **LG1 being lifted to the VML** and the Eigenerklärung requirement — exactly the "floor + paperwork, not tariff body" outcome.

---

## 9. Reference data: sourcing & versioning (critical)

The rules are stable; the **numbers are not**. Every rate is date-bounded and must be sourced, not remembered.

- **Vergabemindestlohn**: per-Land official *Handlungsanleitung* / Tariftreue-Portal of the procuring Land. (The Tarifdatenblatt links to it; the sheet itself does **not** state the €-figure.)
- **Tariflöhne (TV Lohn/Ost etc.)**: the relevant Tarifvertrag text / Tarifregister; mind `valid_from`/`kündbar`.
- **Branchen-Mindestlohn Bau**: AEntG-based, via the SOKA-Bau / BMAS AVE-Verzeichnis.
- **MiLoG**: the Mindestlohnkommission / statutory value.
- **Lohnzusatzkosten components**: current SV employer shares, SOKA-Bau %, BG Bau Gefahrtarif, Umlagen.

Rules:
1. No rate literal in code — all in `data/*.json` with `valid_from`/`valid_to` and `source_url`.
2. Lookups are **point-in-time** by execution date; overlapping validity ranges must be rejected at load time.
3. Keep an `as_of` field so a stored Kalkulation can be reproduced exactly later.

---

## 10. Determinism & guardrails (LLM vs. numeric)

This whole module is a **numeric tool**, not an LLM responsibility — it fits the reasoning/tool separation directly:

- An LLM/agent may **resolve context** (read the Vergabeunterlagen, infer `auftraggeber_typ`, the Ausführungsort, the crew mix, whether Nebenangebote are allowed) and **explain** a result.
- An LLM must **never** produce the wage number, pick the floor, or do the arithmetic. Those go through `floors.py` / `mittellohn.py`, which are pure functions over versioned data.
- The `binding_floor` field exists so the agent can *narrate* ("LG1 was lifted to the Vergabemindestlohn") without *deciding* it.
- Surface, for human review, any item the agent inferred rather than read verbatim — especially `auftraggeber_typ`, `tarifzone`, and crew composition.

---

## 11. Open questions / to confirm before build

1. **Crew mix source**: is the Kolonnenbesetzung an input per Position/Gewerk, a project default, or derived from the LV? (Drives whether `CrewComposition` is per-line or per-project.)
2. **Bauzuschlag convention**: include it inside `ML A` or as a separate line? Pick one and set `includes_bauzuschlag` consistently.
3. **Escalation policy**: model real future tariff steps, or apply a contractual Gleitklausel? Affects `escalation.py` and whether output is a schedule or a single rate.
4. **Multi-Land coverage**: which Bundesländer must the Vergabemindestlohn dataset cover at launch? (Each Land = its own ruleset + figures.)
5. **Threshold awareness**: do you need above-/below-EU-threshold branching now, or only the labor-floor layer (which is largely threshold-agnostic)?
6. **Leiharbeit/Entgeltgleichheit**: in scope as a calculable line, or just a compliance flag for now?

---

## Appendix — Glossary

| Term | Meaning |
|---|---|
| **Tariftreue** | Bidder's binding commitment to pay at least the applicable Tarifvertrag at the place of execution. |
| **Vergabemindestlohn** | Land-specific procurement minimum wage; a **floor** on the productive wage, not a rate. |
| **Mittellohn A / AS / ASL** | Crew-weighted tariff wage / + worker-paid Soziallöhne / + employer Lohnzusatzkosten. ASL = Kalkulationslohn. |
| **Lohnzusatzkosten** | Employer social costs (SV share, SOKA-Bau, BG Bau, Umlagen) loaded on the wage; ~80–95 % in Bauhauptgewerbe. |
| **SOKA-Bau** | Sozialkassen der Bauwirtschaft (ULAK Urlaub, ZVK Zusatzversorgung, Berufsbildung). |
| **Bauzuschlag** | BRTV construction supplement on the tariff wage. |
| **AEntG** | Posting-of-Workers Act; makes AV-tariffs incl. Bau-Mindestlohn binding by **place of work**. |
| **MiLoG** | General statutory minimum wage; absolute floor. |
| **Soziallöhne** | Worker-paid extras (Auslösung, Fahrgeld, VWL) → the "S" in AS. |
| **Beitrittsgebiet / Ost** | Ex-GDR tariff zone (incl. Thüringen & Sachsen-Anhalt), excl. Berlin. |
| **Eigenerklärung (§ 11 TVergG)** | Mandatory tender attachment committing to Tariftreue/Mindestlohn/Entgeltgleichheit. |
