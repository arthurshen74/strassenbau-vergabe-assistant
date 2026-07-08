"""Eval harness for the Phase-3 recipe compiler (KATALOG_AGENT_PHASE3_PLAN.md §7).

For each eval recipe (R1–R4, mined from the real LV data): feed the Kalkulator description to the
katalog_chat agent programmatically (real LLM via OpenRouter, no SSE), then measure

  (a) valid bundle produced + repair iterations used (W18 attempts against the repair budget),
  (b) reuse rate + hits against the recipe's expected-reuse notes,
  (c) activation in a ROLLED-BACK transaction + calculation of a synthetic position (menge from
      the real LV row) — the EKT computes and its EP lands near a plausibility band,
  (d) justification coverage (enforced mechanically by W18; the report shows both lists).

Output: a Markdown report per run under eval/rezept_compiler/. Human-graded; no automated
pass/fail thresholds — four recipes are a judgment set, not a benchmark. The agent's draft
bundles stay in the dev DB for confirm-card review; pass --verwerfen to discard them after
measuring.

    uv run python -m scripts.eval_rezept_compiler [--rezepte R1,R3] [--verwerfen]
"""

from __future__ import annotations

import argparse
import asyncio
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

from langchain_core.messages import AIMessage, ToolMessage

from shared.config import settings
from shared.models.katalog import KatalogStatus
from shared.repositories.katalog import KatalogRepository
from shared.services.kalkulation_v2.positionen import Position
from shared.services.kalkulation_v2.provider import lade_katalog
from shared.services.kalkulation_v2.store import kalkuliere
from shared.services.katalog.chat_agent import KatalogChatAgent
from shared.services.katalog.prompts import load_katalog_handbuch_prompt
from shared.services.katalog.service import KatalogService

from scripts.check_katalog_parity import zustand_sichern

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

WERKZEUG_REZEPT = "rezept_entwurf_speichern"
REPARATUR_BUDGET = 3  # repairs, i.e. max 1 + 3 W18 attempts
RECURSION_LIMIT = 100
BERICHT_VERZEICHNIS = Path(__file__).resolve().parents[2] / "eval" / "rezept_compiler"

# Gate-B simulation: HITL-only kontext variables a recipe may legitimately reuse (no KONSTANTE
# fallback by design). When the deterministic calc reports one unresolvable, the eval supplies the
# answer a Kalkulator would give at Gate B and retries; supplied values land in the report.
GATE_B_ANTWORTEN: dict[str, str] = {
    "materialpreis_eur_pro_t": "120",
    # Foreign geometry a reused chain member may drag in (flagged by the W18 geometry warning);
    # values sized for the R4 patch position (5 t ≈ 25 m² at 8 cm).
    "flaeche_m2": "25",
    "volumen_m3": "2.1",
    "fraesgut_klasse": "1",
    "tiefe_cm": "4",
    "einbaudicke_cm": "4",
    "schichtdicke_m": "0.1",
    "naht_dicke_cm": "4",
    "abstreumenge_kg_pro_m2": "2",
    "bindemittelmenge_kg_pro_m2": "0.3",
    "ev2_ziel": "100",
    "markierung_leistung_m_pro_h": "100",
    "fugenspalttiefe_mm": "15",
    "fugenspaltbreite_mm": "10",
}
_NICHT_AUFLOESBAR = re.compile(r"'([^']+)' nicht auflösbar")


@dataclass
class EvalRezept:
    kennung: str
    titel: str
    beschreibung: str          # the Kalkulator description — the compiler's input
    lv_langtext: str           # the real LV Langtext, report context only
    menge: Decimal             # from the real LV row
    einheit: str
    erwartete_wiederverwendung: set[str]
    ep_hinweis: tuple[str, str]  # plausibility band (report-only), €/einheit


REZEPTE: list[EvalRezept] = [
    EvalRezept(
        kennung="R1",
        titel="Bordstein aufnehmen (m)",
        beschreibung=(
            "Tiefborde aufnehmen: Betonfundament mit dem Bagger aufstemmen, Bordsteine aufnehmen "
            "— die brauchbaren säubern wir und stapeln sie auf Paletten, der Rest geht mit dem "
            "Aufbruch zur Verwertung. Zwei Mann und ein Bagger, etwa 25 Meter die Stunde. Für die "
            "Entsorgung rechnen wir Fundament plus Ausschuss mit rund 60 Kilo je Meter zum "
            "Betonaufbruch-Satz, dazu Abtransport je Tonne und Kilometer zur Deponie."
        ),
        lv_langtext=(
            "Bordstein aufnehmen. Bordstein = Tiefbordstein aus Beton, Höhe bis 30 cm. Fundament "
            "aus Beton, bis 10 cm dick, aufbrechen. Wiederverwendbare Bordsteine säubern, auf "
            "Paletten stapeln, innerhalb der Baustelle fördern und sortiert lagern. Aufbruchgut "
            "und nicht wiederverwendbare Bordsteine durch den AN einer Verwertung zuführen, "
            "AVV-Nr.: 170101, Entsorgung wird gesondert vergütet. Erforderliche Erdarbeiten "
            "ausführen, Boden im Aushubbereich verteilen."
        ),
        menge=Decimal("16"),
        einheit="m",
        erwartete_wiederverwendung={
            "AA_BAGGER", "laenge_m", "anzahl_arbeiter", "stundenlohn_eur",
            "transport_eur_pro_t_km", "entfernung_deponie_km",
        },
        ep_hinweis=("10", "80"),
    ),
    EvalRezept(
        kennung="R2",
        titel="Schieberkappe auf Höhe setzen (St)",
        beschreibung=(
            "Schieberkappen regulieren: je Stück die Kappe freilegen, provisorisch auflegen und "
            "beim Deckeneinbau Zug um Zug auf planmäßige Höhe setzen. Reine Handarbeit — zwei "
            "Mann schaffen etwa vier Kappen die Stunde, kleines Gerät. Die höhenverstellbare "
            "Kappe stellt der Auftraggeber; wir setzen je Stück fünf Euro Mörtel und "
            "Kleinmaterial an."
        ),
        lv_langtext=(
            "Schieberkappe des AG mit Deckel (nach DIN 4056), Gehäuse aus PA+, Deckel aus GJL, "
            "Bolzen und Steg aus Niro A2-70, höhenverstellbar. Schieberkappe zunächst provisorisch "
            "auflegen und entsprechend dem Bauablauf Zug um Zug bis auf planmäßige Höhe setzen. "
            "Oberflächen: in bituminöser Oberfläche."
        ),
        menge=Decimal("1"),
        einheit="St",
        erwartete_wiederverwendung={
            "AA_KOLONNE", "anzahl_st", "anzahl_arbeiter", "stundenlohn_eur",
        },
        ep_hinweis=("20", "120"),
    ),
    EvalRezept(
        kennung="R3",
        titel="Risse im Fräs-Verguss-Verfahren sanieren (m)",
        beschreibung=(
            "Rissanierung im Fräs-Verguss-Verfahren: Riss mit der kleinen Rissfräse auffräsen, "
            "ausblasen und bei Nässe trocknen, Flanken vorstreichen, mit Spezialbitumen vergießen "
            "und mit dem Ziehschuh abdecken. Trupp mit drei Mann und Vergusskocher, rund 60 Meter "
            "die Stunde. Vergussmasse etwa 0,4 Kilo je Meter, Voranstrich rechnen wir pauschal je "
            "Meter."
        ),
        lv_langtext=(
            "Offene Längs-/Querrisse bzw. Längs-/Quernähte mittels Fräse auffräsen. Bei einer "
            "Rissbreite von 2 bis 12 mm: Fräsbreite 8–14 mm, Frästiefe 15–20 mm. Lose Teile "
            "entfernen sowie bei Nässe Fräsbereich trocknen. Rissflanken mit Voranstrichmittel "
            "anstreichen. Der Füllraum ist mit Spezialbitumen zu vergießen und danach unter "
            "Verwendung eines Ziehschuhes mit gleichem Material abzudecken "
            "(Fräs-Verguss-Verfahren)."
        ),
        menge=Decimal("2700"),
        einheit="m",
        erwartete_wiederverwendung={"laenge_m", "anzahl_arbeiter", "stundenlohn_eur"},
        ep_hinweis=("1.5", "15"),
    ),
    EvalRezept(
        kennung="R4",
        titel="Schadstellen mit dem Thermocontainer sanieren (t)",
        beschreibung=(
            "Schadstellensanierung mit dem Thermocontainer: Schadstelle ausschneiden oder "
            "-fräsen, säubern, anspritzen, mit AC 8 D N aus dem Thermocontainer verfüllen und mit "
            "Rüttelplatte oder kleiner Walze verdichten. Abgerechnet wird je eingebauter Tonne. "
            "Drei Mann mit dem Thermocontainer auf dem Lkw, etwa anderthalb Tonnen die Stunde. "
            "Material frei Bau, Emulsion anteilig, Fräsgut-Entsorgung anteilig je Tonne."
        ),
        lv_langtext=(
            "Sanierung von Schadstellen mittels Asphaltthermocontainer AC 8 D N. Schadhafte "
            "Asphaltschicht mit Asphaltbeton AC 8 D N verschließen. Flächengrößen: 1,00 m² bis "
            "8,00 m². Es sind alle notwendigen Arbeitsleistungen einschließlich Material, Geräte "
            "und Arbeitskräfte einzurechnen. Entfernen des Asphalts durch Schneiden, Stemmen oder "
            "Fräsen, Säubern und Trocknen, Anspritzen mit Bitumenemulsion sowie Verdichten des "
            "Einbauasphalts."
        ),
        menge=Decimal("5"),
        einheit="t",
        erwartete_wiederverwendung={
            "menge_t", "anzahl_arbeiter", "stundenlohn_eur",
            "transport_eur_pro_t_km", "entsorgung_fraesasphalt_eur_pro_t",
        },
        ep_hinweis=("100", "500"),
    ),
]


@dataclass
class RezeptErgebnis:
    rezept: EvalRezept
    dauer_s: float = 0.0
    werkzeug_folge: list[str] = field(default_factory=list)
    versuche: list[dict[str, Any]] = field(default_factory=list)  # W18 envelopes, in order
    antwort: str = ""              # the agent's final chat answer
    lauf_fehler: str | None = None  # agent run aborted (recursion limit, API error)
    kalkulation: dict[str, Any] | None = None
    kalkulation_fehler: str | None = None

    @property
    def letzter(self) -> dict[str, Any] | None:
        return self.versuche[-1] if self.versuche else None

    @property
    def bundle_uuid(self) -> str | None:
        env = self.letzter
        return env.get("bundle_uuid") if env else None

    @property
    def reparaturen(self) -> int:
        return max(0, len(self.versuche) - 1)

    @property
    def geminzte_formeln(self) -> int:
        """New BASE formulas the recipe minted (§4 gate: 0 for a standard recipe — every step should
        instantiate an existing base formula)."""
        env = self.letzter or {}
        return len((env.get("entwurf") or {}).get("formeln") or [])


async def baue_agent(engine: AsyncEngine) -> KatalogChatAgent:
    """The katalog_chat agent exactly as the app constructs it (same model/prompt/tools). Loads the
    LIVE Katalog-Handbuch prompt version, so the eval measures whatever is currently seeded/edited."""
    async with engine.connect() as conn:
        handbuch = await load_katalog_handbuch_prompt(conn)
    return KatalogChatAgent(
        engine=engine,
        system_prompt=handbuch.system_prompt,
        chat_model=handbuch.model_name,
        temperature=handbuch.temperature,
    )


def _kurz(args: dict[str, Any]) -> str:
    """One-line tool-call summary for the transcript (W18 args are summarised per section)."""
    if "bundle" in args:
        bundle = args.get("bundle") or {}
        teile = [f"{k}:{len(v)}" for k, v in bundle.items() if isinstance(v, (list, dict)) and v]
        return (
            f"bundle[{', '.join(teile)}] "
            f"wiederverwendung:{len(args.get('wiederverwendung') or [])} "
            f"neu:{len(args.get('neu') or [])}"
        )
    kurz = ", ".join(f"{k}={v!r}" for k, v in args.items() if v is not None)
    return kurz[:140]


async def fahre_rezept(engine: AsyncEngine, rezept: EvalRezept) -> RezeptErgebnis:
    """One compile run: user prompt = the Kalkulator description (§7)."""
    ergebnis = RezeptErgebnis(rezept=rezept)
    agent = await baue_agent(engine)
    # One-shot harness: there is no follow-up turn, so the prompt authorises assumptions the
    # production chat would clarify conversationally.
    prompt = (
        f"Lege ein neues Rezept an. Der Kalkulator beschreibt es so:\n\n„{rezept.beschreibung}“\n\n"
        "Ich bin bis Feierabend nicht erreichbar — Rückfragen kann ich nicht beantworten. "
        "Triff bei offenen Punkten selbst sinnvolle, konservative Annahmen, nenne sie in deiner "
        "Antwort, und speichere den Entwurf JETZT mit rezept_entwurf_speichern. Ich prüfe alles "
        "auf der Bestätigungskarte."
    )
    start = time.monotonic()
    try:
        zustand = await agent.ainvoke(
            [{"role": "user", "content": prompt}], recursion_limit=RECURSION_LIMIT
        )
    except Exception as exc:  # eval boundary: an aborted run is a finding, not a crash
        ergebnis.lauf_fehler = f"{type(exc).__name__}: {exc}"
        ergebnis.dauer_s = time.monotonic() - start
        return ergebnis
    ergebnis.dauer_s = time.monotonic() - start

    for m in zustand["messages"]:
        if isinstance(m, AIMessage):
            for tc in m.tool_calls or []:
                ergebnis.werkzeug_folge.append(f"{tc['name']}({_kurz(tc.get('args') or {})})")
        if isinstance(m, ToolMessage) and m.name == WERKZEUG_REZEPT:
            artefakt = getattr(m, "artifact", None)
            if isinstance(artefakt, dict):
                ergebnis.versuche.append(artefakt)
    letzte = zustand["messages"][-1]
    if isinstance(letzte, AIMessage):
        ergebnis.antwort = str(letzte.content)
    return ergebnis


async def aktiviere_und_kalkuliere(
    engine: AsyncEngine, bundle_uuid: UUID, leistung_code: str, rezept: EvalRezept
) -> dict[str, Any]:
    """Measurement (c): activate the draft bundle INSIDE a transaction, load the catalog from that
    uncommitted state, calculate the synthetic position, then roll everything back. The dev DB and
    the running engine dicts are untouched afterwards."""
    async with engine.connect() as conn:
        trans = await conn.begin()
        try:
            repo = KatalogRepository(conn)
            gruppen = await repo.nach_bundle(bundle_uuid)
            for entitaet, zeilen in gruppen.items():
                for z in zeilen:
                    if z.status == KatalogStatus.ENTWURF:
                        await repo.aktiviere(entitaet, z.zeile_uuid)
            await repo.preise_aktivieren(bundle_uuid)
            with zustand_sichern():
                await lade_katalog(conn)
                # Gate-B simulation: supply the Kalkulator's answer for HITL-only kontext
                # variables the recipe reuses, one per retry.
                kontext: dict[str, Decimal] = {}
                while True:
                    try:
                        r = kalkuliere(Position(
                            oz=rezept.kennung, leistung_key=leistung_code,
                            menge=rezept.menge, kontext=kontext,
                        ))
                        break
                    except ValueError as exc:
                        m = _NICHT_AUFLOESBAR.search(str(exc))
                        name = m.group(1) if m else None
                        if name is None or name in kontext or name not in GATE_B_ANTWORTEN:
                            raise
                        kontext[name] = Decimal(GATE_B_ANTWORTEN[name])
                # Materialise before the dicts are restored / the txn rolls back.
                return {
                    "ekt_eur": str(r["ekt_eur"].quantize(Decimal("0.01"))),
                    "ep_eur": str(r["ep_eur"]),
                    "einheit": r["einheit"],
                    "bauverfahren": r["bauverfahren"],
                    "kontext_nachgereicht": {k: str(v) for k, v in kontext.items()},
                    "detail": [
                        {
                            "vorgang": d["vorgang"],
                            "ekt_eur": str(d["ekt_eur"]),
                            "positionen": [
                                f"{p['kostenart']}: {p['betrag_eur']} € ({p['variable']}, {p['quelle']})"
                                for p in d["positionen"]
                            ],
                        }
                        for d in r["detail"]
                    ],
                }
        finally:
            await trans.rollback()


# --------------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------------- #
def _md_liste(eintraege: list[dict[str, Any]], warum_feld: str) -> list[str]:
    return [f"| `{e.get('code')}` | {e.get(warum_feld, '')} |" for e in eintraege]


def schreibe_bericht(ergebnisse: list[RezeptErgebnis], pfad: Path) -> None:
    z: list[str] = [
        "# Rezept-Compiler Eval",
        "",
        f"Lauf: {datetime.now().isoformat(timespec='seconds')} · Modell: laut seeder "
        f"`katalog_handbuch`-Prompt (Frontmatter) · Reparaturbudget: {REPARATUR_BUDGET}",
        "",
        "| Rezept | gültig | Reparaturen | Wiederverwendungsquote | erwartete Treffer | "
        "geminzte Formeln | EP | Hinweisband | Dauer |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for e in ergebnisse:
        env = e.letzter or {}
        wieder = env.get("wiederverwendung") or []
        neu = env.get("neu") or []
        quote = f"{len(wieder)}/{len(wieder) + len(neu)}" if (wieder or neu) else "—"
        codes = {x.get("code") for x in wieder}
        treffer = len(e.rezept.erwartete_wiederverwendung & codes)
        ep = e.kalkulation["ep_eur"] if e.kalkulation else "—"
        lo, hi = e.rezept.ep_hinweis
        # §4 gate: 0 minted formulas for a standard recipe (flag any as ⚠).
        formeln = f"⚠ {e.geminzte_formeln}" if e.geminzte_formeln else "0"
        z.append(
            f"| {e.rezept.kennung} {e.rezept.titel} | {'ja' if e.bundle_uuid else 'NEIN'} "
            f"| {e.reparaturen} | {quote} | {treffer}/{len(e.rezept.erwartete_wiederverwendung)} "
            f"| {formeln} | {ep} €/{e.rezept.einheit} | {lo}–{hi} | {e.dauer_s:.0f}s |"
        )
    z.append("")
    gesamt_geminzt = sum(e.geminzte_formeln for e in ergebnisse)
    gueltig = sum(1 for e in ergebnisse if e.bundle_uuid)
    z += [
        f"**Gate (§4):** {gueltig}/{len(ergebnisse)} Rezepte gültig · "
        f"{gesamt_geminzt} geminzte Basisformeln (Ziel 0 für Standardrezepte).",
        "",
    ]

    for e in ergebnisse:
        env = e.letzter or {}
        z += [f"## {e.rezept.kennung} — {e.rezept.titel}", ""]
        z += ["**Kalkulator-Beschreibung (Eingabe):**", f"> {e.rezept.beschreibung}", ""]
        z += ["**LV-Langtext (Original, nur Kontext):**", f"> {e.rezept.lv_langtext}", ""]

        z += [
            f"**Ergebnis:** {'Entwurf gespeichert' if e.bundle_uuid else 'KEIN gültiger Entwurf'} · "
            f"W18-Versuche: {len(e.versuche)} (Reparaturen: {e.reparaturen}, Budget: {REPARATUR_BUDGET}) · "
            f"Dauer {e.dauer_s:.0f}s",
        ]
        if e.bundle_uuid:
            z.append(f"· `bundle_uuid: {e.bundle_uuid}` (Entwurf liegt zur Karten-Prüfung im Katalog)")
        if e.lauf_fehler:
            z.append(f"**Lauf abgebrochen:** `{e.lauf_fehler}`")
        z.append("")

        gescheitert = [v for v in e.versuche if not v.get("bundle_uuid")]
        if gescheitert:
            z.append("**Reparaturschleife (Fehler je gescheitertem Versuch):**")
            for i, versuch in enumerate(e.versuche, start=1):
                if versuch.get("bundle_uuid"):
                    continue
                for f in (versuch.get("bericht") or {}).get("fehler", []):
                    z.append(f"- Versuch {i}: {f}")
            z.append("")

        wieder = env.get("wiederverwendung") or []
        neu = env.get("neu") or []
        if wieder:
            z += ["**Wiederverwendung:**", "", "| Code | warum |", "|---|---|"]
            z += _md_liste(wieder, "warum")
            z.append("")
        if neu:
            z += ["**Neu geprägt:**", "", "| Code | warum nicht vorhanden |", "|---|---|"]
            z += _md_liste(neu, "warum_nicht_vorhanden")
            z.append("")
        codes = {x.get("code") for x in wieder}
        fehlend = e.rezept.erwartete_wiederverwendung - codes
        if fehlend:
            z.append(
                f"**Erwartete Wiederverwendung NICHT getroffen:** {', '.join(sorted(fehlend))}"
            )
            z.append("")

        warnungen = env.get("warnungen") or []
        if warnungen:
            z += ["**Dubletten-Warnungen:**"] + [f"- {w}" for w in warnungen] + [""]

        formeln = (env.get("entwurf") or {}).get("formeln") or []
        if formeln:
            z += ["**Formeln:**", ""]
            for f in formeln:
                einheit = f" [{f['einheit']}]" if f.get("einheit") else ""
                z.append(f"- `{f.get('name')}{einheit} = {f.get('ausdruck')}`")
            z.append("")

        if e.kalkulation:
            k = e.kalkulation
            lo, hi = e.rezept.ep_hinweis
            z += [
                f"**Kalkulation (aktiviert in zurückgerollter Transaktion, Menge "
                f"{e.rezept.menge} {e.rezept.einheit} aus der realen LV-Zeile):**",
                "",
                f"- EKT {k['ekt_eur']} € · EP {k['ep_eur']} €/{k['einheit']} "
                f"(Hinweisband {lo}–{hi} €/{e.rezept.einheit}) · Bauverfahren `{k['bauverfahren']}`",
            ]
            if k.get("kontext_nachgereicht"):
                nachgereicht = ", ".join(f"{n}={w}" for n, w in k["kontext_nachgereicht"].items())
                z.append(f"- Gate-B-Simulation (nachgereichte Kontextwerte): {nachgereicht}")
            for d in k["detail"]:
                z.append(f"- `{d['vorgang']}` — {d['ekt_eur']} €")
                z += [f"  - {p}" for p in d["positionen"]]
            z.append("")
        elif e.kalkulation_fehler:
            z += [f"**Kalkulation FEHLGESCHLAGEN:** `{e.kalkulation_fehler}`", ""]

        if e.werkzeug_folge:
            z += ["<details><summary>Werkzeug-Trace</summary>", ""]
            z += [f"{i}. `{w}`" for i, w in enumerate(e.werkzeug_folge, start=1)]
            z += ["", "</details>", ""]

        if e.antwort:
            z += ["<details><summary>Agent-Antwort (Chat)</summary>", "", e.antwort, "", "</details>", ""]

    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text("\n".join(z), encoding="utf-8")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Rezept-Compiler-Eval (R1–R4) gegen die dev DB.")
    parser.add_argument("--rezepte", help="Komma-Liste (z. B. R1,R3); Standard: alle")
    parser.add_argument(
        "--verwerfen", action="store_true",
        help="die erzeugten Entwurfs-Bundles nach der Messung verwerfen",
    )
    args = parser.parse_args()

    gewuenscht = {k.strip().upper() for k in args.rezepte.split(",")} if args.rezepte else None
    auswahl = [r for r in REZEPTE if gewuenscht is None or r.kennung in gewuenscht]

    engine = create_async_engine(settings.database_url)
    ergebnisse: list[RezeptErgebnis] = []
    try:
        for rezept in auswahl:
            print(f"[{rezept.kennung}] {rezept.titel} …", flush=True)
            e = await fahre_rezept(engine, rezept)
            if e.bundle_uuid:
                env = e.letzter or {}
                leistungen = (env.get("entwurf") or {}).get("leistungen") or []
                leistung_code = leistungen[0]["code"] if leistungen else env.get("schluessel", "")
                try:
                    e.kalkulation = await aktiviere_und_kalkuliere(
                        engine, UUID(e.bundle_uuid), leistung_code, rezept
                    )
                except Exception as exc:  # eval boundary: report, never crash the run
                    e.kalkulation_fehler = f"{type(exc).__name__}: {exc}"
            ergebnisse.append(e)
            status = "ok" if e.bundle_uuid else "UNGÜLTIG"
            ep = e.kalkulation["ep_eur"] if e.kalkulation else "—"
            print(
                f"[{rezept.kennung}] {status} · Reparaturen {e.reparaturen} · EP {ep} "
                f"· {e.dauer_s:.0f}s",
                flush=True,
            )
            if args.verwerfen and e.bundle_uuid:
                await KatalogService(engine).bundle_verwerfen(UUID(e.bundle_uuid))
                print(f"[{rezept.kennung}] Entwurf verworfen.", flush=True)

        stempel = datetime.now().strftime("%Y%m%d_%H%M%S")
        pfad = BERICHT_VERZEICHNIS / f"bericht_{stempel}.md"
        schreibe_bericht(ergebnisse, pfad)
        print(f"Bericht: {pfad.resolve()}")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
