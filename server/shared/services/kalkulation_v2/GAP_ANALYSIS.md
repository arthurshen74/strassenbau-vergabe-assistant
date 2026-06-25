# Catalog Gap Analysis — kalkulation_v2 vs. the ingested LV corpus

Scope: the 9 ingested LVs in the `roadbuilders` Postgres (`lv_items`, 1147
Normalpositionen). Compared against the current catalog spine (`leistungen.py`,
`bauverfahren.py`, `vorgaenge.py`, `ausfuehrungsarten.py`, `leistung_bauverfahren.py`)
and the variable layer (`formel.py`, `stammdaten.py`, `materialien.py`).

Filter applied per request: **kept** milling, ground prep / earthwork, FSS &
unbound base, asphalt, shoulder (Bankett). **Skipped** Verkehrssicherung,
Baustelleneinrichtung / setup-teardown / documentation overhead, and
gardening / vegetation. Kerbs-paving, drainage/manholes, and marking *application*
are present in the corpus but fall outside the stated scope — listed in §7 for a
go/no-go decision, not counted as in-scope gaps.

The catalog was authored almost entirely against **one** LV (the L 101
mill-and-fill, `ceb64763…`, 268 positions). It models that job well. The other
eight LVs are where the gaps are.

---

## 0. The headline — why `AC 11 D S` isn't found

The example position —
*"Asphaltdeckschicht aus Asphaltbeton AC 11 DS … BK 1,0 … Einbau nach
Einbaumenge = 63 kg/m² entspricht 2,5 cm, Bindemittel 50/70 … obere Schicht
einer kompakten Asphaltbefestigung heiß-auf-heiß"* — **is** the top course of a
mill-and-fill. It is missing for **two structural reasons**, not one missing row:

1. **Mixes are modeled as Leistungen, one per mix.** The catalog hardcodes a
   single mix per layer role: `L_ASPHALT_DECK_AC8` = *AC 8 D S*,
   `L_ASPHALT_BINDER_AC16` = *AC 16 B S*, `L_ASPHALTTRAGSCHICHT` = *AC 32 T S*,
   `L_ASPHALT_TRAGSCHICHT_AC22` = *AC 22 T S*, `L_GUSSASPHALT_DECK` = *MA 8 S*.
   `AC 11 D S` has no row, so it cannot be classified. The corpus actually uses
   **21 distinct mix designations** (see §3) — one-Leistung-per-mix does not scale.

2. **The `kg/m²` Einbaumenge spec has no bridge.** This position is booked in
   **m²** but specifies the lift as **63 kg/m²** (≙ 2,5 cm). Other LVs book the
   *same* deck course in **t**. The catalog only bridges m²→t via an
   `einbaudicke_cm` × density path; there is no `kg/m² ↔ cm ↔ t` conversion. See §6.

The fix for (1) is the master-data move already flagged in `ARCHITECTURE.md §5`:
**one Leistung per layer *role*, mix designation as a `Baustoff`** (density +
supplier price), with binder / class / Einbaumenge as context values.

---

## 1. Coverage summary by trade

| Trade | Catalog state | Gap size |
|---|---|---|
| Milling (fräsen) | good (3 depth bands + fein/nach) | small — 2 deeper bands + Profilfräsen |
| Asphalt mixes | 1 mix per layer role | **large** — see §3 |
| Asphalt removal (aufnehmen) | only `L_AUFBRECHEN` (Randstreifen) | medium — deep/area-classed removal |
| Asphalt repair (Schadstellen) | none | **large** — whole method family |
| FSS / unbound base | herstellen only | medium — aufnehmen + stabilization |
| Earthwork / ground prep | BKl 3–5, planum, verdichten | medium — Fels, exchange, trenching |
| Shoulder (Bankett) | B2 mineral shoulder | medium — Bankettbeton, precast, units |

---

## 2. Milling (fräsen)

Covered: `L_FRAESEN_1_25 / _3_45 / _5_9`, `L_NACHFRAESEN`, `L_FEINFRAESEN`
(`BV_FRAESEN` / `BV_FEINFRAESEN`, Kaltfräse).

Gaps:

- **Deeper milling bands.** Corpus has *Tiefe ü.6-8 cm* and *ü.8-10 cm*
  (ATS/ATD, e.g. `9ebd4074`, `77b03e0c`). Catalog tops out at 5–9 cm.
  → add `L_FRAESEN_6_8`, `L_FRAESEN_8_10` (reuse `BV_FRAESEN`; productivity
  falls with depth — a `stammdaten` curve, not new machinery).
- **Profilfräsen** (`03cacd5a`, *Asphalt profilfräsen*) — variable-depth
  levelling cut, no fixed band; distinct productivity. → own Leistung, reuse
  Kaltfräse.
- Width-classed Feinfräsen (bis 30 / 30–50 / 50–100 / 150–200 / >200 cm) and
  *feinstfräsen* for marking removal are productivity refinements on
  `L_FEINFRAESEN`, not new Leistungen.

Layers needed: Leistung + mapping only; Stammdaten depth/width productivity.

---

## 3. Asphalt — the largest gap

The corpus uses these mix designations (position counts in parentheses):

```
Deck:        AC 8 D S ✓(15)   AC 11 D S ✗(8)   AC 8 D N ✗(4)   AC 5 D L ✗(1)
Gussasphalt: MA 8 S ✓(28)     MA 11 S ✗(2)
Thin/seal:   DSK 5 ✓(8)       AC 8 DSH-V ✗(3)
Binder:      AC 16 B S ✓(8)   AC 22 B S ✗(14)
Base:        AC 32 T S ✓      AC 22 T S ✓(14)  AC 16 T S ✗(6)  AC 22 T N ✗(5)
Trag-deck:   AC 16 T D ✗(7)   (combined base+wearing course — new layer role)
Unbound:     "Deckschicht ohne Bindemittel" / DoB ✗(10)
```

✓ = a Leistung exists, ✗ = gap.

### 3a. Mix-as-master-data (the structural fix)

Collapse the per-mix Leistungen into **one Leistung per layer role**:
`L_ASPHALT_DECK`, `L_ASPHALT_BINDER`, `L_ASPHALT_TRAG`, `L_ASPHALT_TRAGDECK`,
`L_GUSSASPHALT_DECK`. The **mix designation becomes a `Baustoff`** in
`materialien.py` (carrying `rohdichte_t_pro_m3` and a supplier price via
`lieferanten_preise.py`); binder (50/70, 25/55-55A, PmB, 30/45 …), Belastungsklasse,
and Einbaumenge are context values. This directly answers AC 11 D S and every
future mix at once, and closes the `ARCHITECTURE.md §5` "asphalt not in master
data" known gap (asphalt is 86–93 % of these positions' cost).

Recipe reuse: all hot AC mixes reuse `BV_ASPHALT_EINBAU` (Fertiger+Beschicker)
or `BV_ASPHALT_HAND`; MA reuses `BV_GUSSASPHALT`.

### 3b. New layer role: Asphalttragdeckschicht (AC 16 T D)

Combined base/wearing course laid as a single lift on low-traffic roads
(`2a4d7c80`, `77b03e0c`, `9a676bae`). Distinct from Trag- and Deckschicht.
→ `L_ASPHALT_TRAGDECK` + mapping to `BV_ASPHALT_EINBAU`.

### 3c. Deck/binder/base in N-class binder (AC 8 D N, AC 22 T N)

"N" (Normal) vs "S" (Stress) is a class/binder context value once mixes are
master data — but today there is no row at all. Covered for free by 3a.

### 3d. Specialty surfaces — genuinely new methods

- **DSH-V** (*AC 8 DSH-V*, `5183effb`) — thin layer in **hot** placement on a
  seal, Einbaumenge 50 kg/m². Distinct from cold `DSK`. → `L_DSH_V` + likely a
  variant of `BV_ASPHALT_EINBAU`/`BV_DSK`.
- **Gussasphaltoberfläche bearbeiten / abstreuen** (Verfahren A, B 2/3;
  2/5 split at 12–15 kg/m²; `2a4d7c80`, `ceb64763`, `9ebd4074`, `77b03e0c`) —
  pressing chippings into the mastic surface. Distinct from `L_ABSTUMPFUNG`
  (LFK 1/3 at 1 kg/m²). → own Leistung + Vorgang (Abstreuer at a different rate).

### 3e. Asphalt removal — Asphaltbefestigung aufnehmen

`L_AUFBRECHEN` only covers *Randstreifen mit SoB*. The corpus has general
*Asphaltbefestigung aufnehmen* classed by **Dicke** (ü.6-12, 12-18, 24-30 cm)
and **Tiefe** (ü.10-20, 20-30, 30-45 cm), booked in **m² and m³**, plus
*Asphalt auf Kleinflächen aufnehmen* (`ceb64763`, `9a676bae`, `03cacd5a`).
→ depth/area-classed removal Leistung(en); recipe `BV_AUFBRECHEN` exists,
needs depth-driven productivity + m³ geometry.

### 3f. Schadstellensanierung / patch repair (whole new family)

LV `6d9116ab` is an entire surface-repair tender, unmodeled:
- *Sanierung Schadstellen Thermocontainer AC 8 D N* (hot-box patching, t).
- *Schadstellen anspritzen und abstreuen — Reparaturzug, BE C67BP3-REP 5/8,
  11–17 kg/m²* (spray-and-chip / Oberflächenbehandlung).
- *Fugenfüllung ersetzen* (joint refill on existing pavement).
→ new method family: Thermocontainer/Reparaturasphalt Ausführungsart,
surface-dressing Vorgang, repair-rate Stammdaten. Large, self-contained.

### 3g. Minor asphalt items

Asphaltaufkantung (`9a676bae`), *Streifen/Rinnen aus MA 8 S* (gutter from mastic,
`ceb64763`), **B-Fugenband** anschluss (preformed bitumen tape — distinct from
Fugenmasse N2 and from the PmB band in `L_NAHT`), **Fugenmasse N1** vs N2,
Asphaltvlies (vs the grid in `L_ASPHALTEINLAGE`). Small; fold into existing
Naht/Fugen/Grid families with material/rate variants.

---

## 4. FSS & unbound base

Covered: `L_FSS_EV45`, `L_FSS_EV100` (FSS 0/32; 0/45 and UF3 are Körnung
context), `L_STS` (Schottertragschicht). Recipes `BV_FSS_GRADER/FERTIGER`.

Gaps:

- **Schicht ohne Bindemittel aufnehmen** (STS / STS+DoB take-up, classed by
  Dicke; `3775f391`, `2a4d7c80`) — removal of unbound base, distinct from
  *herstellen*. → Leistung + a take-up Vorgang (Bagger/Lader + Abtransport).
- **Bodenverfestigung / Verfestigung mit Bindemittel** (`9a676bae`,
  *Verfestig. m. Bindem. herst.*, m³) — cement/lime stabilization (HGT-style).
  Unmodeled. → new Leistung + Vorgang (binder spreader + mixer/pulvimixer);
  binder-rate Stammdaten.
- **Bodenaustausch / mechanische Bodenverbesserung** (`9a676bae`, `03cacd5a`).
  Overlaps stabilization; decide whether one "subgrade improvement" family
  covers both.

---

## 5. Earthwork / ground prep

Covered: `L_BANKETT_ABTRAGEN`, `L_BODEN_EINBAU_GROBK`, `L_OBERBODEN`,
`L_BODEN_LOESEN` (BKl 3–5), `L_PLANUM`, `L_PLANUM_VERDICHTET`,
`L_BODEN_VERDICHTEN`.

Gaps:

- **Fels / Bodenklasse 6–7 lösen** (`9a676bae`, *Boden bzw. Fels lösen und
  verwerten*). `L_BODEN_LOESEN` is BKl 3–5 only; rock needs ripper/breaker
  productivity. → class-driven Leistung/productivity.
- **Trenching for utilities/foundations** — *Leitungsgraben*, *Fundamentgraben*,
  *Suchgraben*, *Abbruchbaugrube/Kopfloch* (`ceb64763`, `77b03e0c`), booked in
  m and m³ with Aushub verwerten/entsorgen. In scope as "digging". → excavation
  Leistung family by Tiefe/BKl + backfill/disposal.
- Bodenaustausch — see §4.

---

## 6. Shoulder (Bankett)

Covered: `L_BANKETT_ABTRAGEN`, `L_BANKETTBEF_B2` (B2 0/32 mineral shoulder;
`BV_BANKETT_GRADER/FERTIGER`).

Gaps:

- **Bankettbeton** (`03cacd5a`, *Bankettbeton liefern und einbauen* + *nachbehandeln*
  + Nachweis Querneigung) — concrete shoulder, distinct from B2 mineral. Needs a
  concrete `Baustoff` and a curing (Nachbehandlung) step.
- **Fertigteil-Bankettplatten** (`77b03e0c`, precast slabs + *schneiden*) —
  precast shoulder, new Ausführungsart.
- **Unit duality.** Bankett profilgerecht herstellen is booked across **m, m², t,
  m³** in different LVs. Same need as asphalt §3 / the kg/m² bridge below.

### Cross-cutting: the measurement bridge

`Store._GEOM` maps `m2/m/m3/t`. What's missing is the conversion web the corpus
actually uses:

- **kg/m² → cm → t** for asphalt/thin layers booked in m² or t with an
  Einbaumenge in kg/m² (AC 11 D S = 63 kg/m² = 2,5 cm; DSH-V = 50 kg/m²;
  DSK 5 = 18 kg/m²; abstreuen = 12–15 kg/m²).
- **m (length) → m²/m³/t** for linear shoulder/strip positions given a Breite +
  Dicke.

→ `formel.py`: `einbaudicke_cm = einbaumenge_kg_m2 / (dichte_asphalt × 10)` and
`menge_t = flaeche_m2 × einbaumenge_kg_m2 / 1000`; plus a length→area bridge.
`stammdaten.py`/`materialien.py`: per-mix density.

---

## 7. Present in the corpus but outside the stated scope (decide)

Not counted above; flag for a go/no-go because they recur heavily:

- **Marking *application*** — Längs-/Quer-/Pfeilmarkierung Typ II, P6/P7,
  Heißplastik / Kaltspritzplastik, plus Markierungsfläche reinigen/trocknen.
  The catalog only *removes* markings (`L_MARK_*`). ~30+ positions.
- **Kerbs & paving** (Borde, Pflaster, Rinnen, Naturstein) — whole trade, ~40
  positions. Not in catalog.
- **Drainage / manholes** (Schächte, Straßenabläufe, Rohre, Leitungszone) —
  whole trade, ~58 positions. Not in catalog.
- **Bohrkerne / Kontrollprüfungen / Plattendruckversuche / FDVK** — QA/testing
  overhead; usually Psch/St lump items.

---

## 8. Suggested priority

1. **Asphalt mix-as-master-data (§3a) + the kg/m² bridge (§6).** Single highest
   leverage: unblocks AC 11 D S, AC 22 B S, AC 16 T S/T N, AC 8 D N, MA 11 S and
   the m²/t duality in one move, on the dominant cost driver.
2. **Asphalttragdeckschicht (§3b)** and **deeper milling bands + Profilfräsen
   (§2)** — cheap, high recurrence, reuse existing recipes.
3. **Asphaltbefestigung aufnehmen, depth/area-classed (§3e)** and **unbound-base
   aufnehmen (§4)** — removal side of mill-and-fill.
4. **Bankettbeton + precast (§6)**, **Fels/trenching (§5)**, **stabilization (§4)**.
5. **Schadstellensanierung family (§3f)** — large but self-contained; do as a
   unit when a repair LV is in play.
6. Decide §7 (marking application / kerbs / drainage) scope before building.
```
