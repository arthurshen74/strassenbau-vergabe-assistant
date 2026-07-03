"""
lese_modell.py — the read layer behind the Katalog-Chat agent's tools (Phase 1, T1–T33).

One class, `LeseModell`, answers every catalog read: enumerations, single-entity detail resolved
one reference deep with its reverse edges, targeted relationship queries, lexical search, formula
rendering, and the transitive variable analyses (derivation tree, where-used). All logic lives here;
the tool handlers are thin wrappers (§1.3). Every tool returns a JSON-compact envelope — short keys,
Decimals/dates stringified, None values dropped — designed for LLM consumption (§2).

The source of truth is the DATABASE (`KatalogRepository`), not the engine's in-memory module dicts
(§1.2): default visibility is `aktiv` rows; drafts and archived versions are reachable only through
the explicit `status` parameter on list tools and through the history/draft tools. Domain objects are
reconstructed from the stored payloads exactly as the provider does; where-used analysis parses the
stored formula expressions via `Formel.eingaben()`. A `LeseModell` caches its loads for its own
lifetime (one tool call), so cross-entity resolution inside a single answer never re-queries a table.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from sqlalchemy.ext.asyncio import AsyncConnection

from shared.models.katalog import KatalogEntitaet, KatalogStatus
from shared.repositories.katalog import KatalogRepository
from shared.services.kalkulation_v2.formel_darstellung import VariablenLegende, stelle_formel_dar
from shared.services.kalkulation_v2.model import (
    AufloesungsMethode,
    Formel,
    VariableDefinition,
    _FUNKTIONEN,
)

# List envelopes carry `treffer_gesamt` so truncation is never silent; `limit` clamps to a hard cap.
LIMIT_STANDARD = 50
LIMIT_MAX = 200

# Precedence for a variable name shadowed across gruppen — mirrors the `{**stamm, **kontext, **formel}`
# merge in store.py, where the FORMEL-gruppe definition wins the runtime KATALOG.
_GRUPPE_RANG = {"stammdaten": 1, "kontext": 2, "formel": 3}

# T3 — the DSL vocabulary. Operators/comparisons are the AST the evaluator accepts; the function
# whitelist is sourced from `_FUNKTIONEN` (extending it is an engineering change, §1.5), each with a
# one-line semantics + example authored here.
_DSL_OPERATOREN = [
    {"symbol": "+", "bedeutung": "Addition", "beispiel": "a + b"},
    {"symbol": "-", "bedeutung": "Subtraktion / Vorzeichen", "beispiel": "a - b"},
    {"symbol": "*", "bedeutung": "Multiplikation", "beispiel": "a * b"},
    {"symbol": "/", "bedeutung": "Division", "beispiel": "a / b"},
    {"symbol": "%", "bedeutung": "Modulo (Rest)", "beispiel": "a % b"},
    {"symbol": "**", "bedeutung": "Potenz", "beispiel": "a ** 2"},
]
_DSL_VERGLEICHE = [
    {"symbol": "<", "bedeutung": "kleiner"},
    {"symbol": "<=", "bedeutung": "kleiner-gleich"},
    {"symbol": ">", "bedeutung": "größer"},
    {"symbol": ">=", "bedeutung": "größer-gleich"},
    {"symbol": "==", "bedeutung": "gleich"},
    {"symbol": "!=", "bedeutung": "ungleich"},
]
_DSL_FUNKTION_DOKU = {
    "abs": ("Betrag", "abs(-3) → 3"),
    "min": ("kleinster Wert", "min(120, 1000 / tiefe_cm)"),
    "max": ("größter Wert", "max(18, 220 / tiefe_cm)"),
    "round": ("auf n Nachkommastellen runden (n=0 Standard)", "round(3.14159, 2) → 3.14"),
    "ceil": ("aufrunden zur nächsten Ganzzahl", "ceil(2.1) → 3"),
    "floor": ("abrunden zur nächsten Ganzzahl", "floor(2.9) → 2"),
}


def _env(obj: Any) -> Any:
    """Normalise an envelope for JSON/LLM consumption: drop None, stringify Decimal/date, unwrap Enum."""
    if isinstance(obj, dict):
        return {k: _env(v) for k, v in obj.items() if v is not None}
    if isinstance(obj, (list, tuple)):
        return [_env(v) for v in obj]
    if isinstance(obj, Decimal):
        return format(obj.normalize(), "f")
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if isinstance(obj, Enum):
        return obj.value
    return obj


def _limit(limit: int | None) -> int:
    return max(1, min(limit or LIMIT_STANDARD, LIMIT_MAX))


def _liste(alle: list[dict], limit: int | None) -> dict[str, Any]:
    """A list envelope: the total match count plus the (clamped) page of entries."""
    n = _limit(limit)
    return {"treffer_gesamt": len(alle), "eintraege": alle[:n]}


def _passt(text: str | None, *felder: str | None) -> bool:
    if not text:
        return True
    n = text.lower()
    return any(f is not None and n in f.lower() for f in felder)


# --------------------------------------------------------------------------- #
# Generic BM25 for T2 (the baustoff_suche._BM25 pattern generalised over catalog documents).
# --------------------------------------------------------------------------- #
_K1 = 1.5
_B = 0.75
_KOERNUNG = re.compile(r"\d+/\d+")
_WORT = re.compile(r"[a-zäöüß0-9]+", re.IGNORECASE)


def _tokenize(text: str) -> list[str]:
    t = text.lower()
    return _KOERNUNG.findall(t) + _WORT.findall(t)


class _Suchindex:
    """Okapi-BM25 over `(schluessel, text)` documents; returns catalog keys ranked by a query."""

    def __init__(self, dokumente: list[dict[str, Any]]) -> None:
        self.docs = dokumente
        self.tf = [Counter(_tokenize(d["_text"])) for d in dokumente]
        self.len = [sum(tf.values()) for tf in self.tf]
        self.avglen = (sum(self.len) / len(dokumente)) if dokumente else 0.0
        n = len(dokumente)
        df: Counter[str] = Counter()
        for tf in self.tf:
            df.update(tf.keys())
        self.idf = {t: math.log(1 + (n - d + 0.5) / (d + 0.5)) for t, d in df.items()}

    def score(self, query: str) -> list[tuple[dict[str, Any], float]]:
        q = set(_tokenize(query))
        ranked: list[tuple[dict[str, Any], float]] = []
        for i, doc in enumerate(self.docs):
            tf, dl = self.tf[i], self.len[i]
            s = 0.0
            for t in q & tf.keys():
                f = tf[t]
                s += self.idf.get(t, 0.0) * (f * (_K1 + 1)) / (
                    f + _K1 * (1 - _B + _B * dl / (self.avglen or 1.0))
                )
            if s > 0:
                ranked.append((doc, s))
        ranked.sort(key=lambda x: x[1], reverse=True)
        return ranked


# Per-entity search config: the display-name builder and the free-text fields to index.
def _name_join(*teile: str | None) -> str:
    return " ".join(t for t in teile if t)


_SUCH_ENTITAETEN: dict[KatalogEntitaet, tuple[Any, tuple[str, ...]]] = {
    KatalogEntitaet.LEISTUNGEN: (lambda p: p.get("name"), ("name", "beschreibung", "standard_kennung")),
    KatalogEntitaet.BAUVERFAHREN: (lambda p: p.get("name"), ("name",)),
    KatalogEntitaet.VORGAENGE: (lambda p: p.get("name"), ("name",)),
    KatalogEntitaet.AUSFUEHRUNGSARTEN: (lambda p: p.get("name"), ("name", "geraetebezug")),
    KatalogEntitaet.BETRIEBSKATEGORIEN: (lambda p: p.get("bezeichnung"), ("bezeichnung", "beschreibung")),
    KatalogEntitaet.BETRIEBSARTEN: (lambda p: p.get("bezeichnung"), ("bezeichnung", "beschreibung")),
    KatalogEntitaet.FORMELN: (lambda p: None, ("ergebnis_variable",)),
    KatalogEntitaet.VARIABLEN: (lambda p: p.get("bezeichnung"), ("bezeichnung", "beschreibung")),
    KatalogEntitaet.GLOBALE_VARIABLEN: (lambda p: p.get("bezeichnung"), ("bezeichnung",)),
    KatalogEntitaet.BAUSTOFFE: (lambda p: p.get("name"), ("name", "kategorie", "koernung")),
    KatalogEntitaet.LIEFERANTEN: (lambda p: p.get("name"), ("name", "standort")),
    KatalogEntitaet.MASCHINEN: (lambda p: _name_join(p.get("hersteller"), p.get("modell")), ("hersteller", "modell")),
}


class LeseModell:
    """Read-only access to the persisted catalog for the agent's tools; one instance per tool call."""

    def __init__(self, conn: AsyncConnection) -> None:
        self.repo = KatalogRepository(conn)
        self._zeilen_cache: dict[tuple[KatalogEntitaet, KatalogStatus], list] = {}
        self._formeln_cache: dict[str, Formel] | None = None
        self._var_index_cache: dict[str, Any] | None = None
        self._bv_vorgaenge_cache: dict[str, list[str]] | None = None
        self._leistung_bv_cache: dict[str, list[str]] | None = None

    # --- cached loaders --------------------------------------------------- #
    async def _zeilen(
        self, entitaet: KatalogEntitaet, status: KatalogStatus = KatalogStatus.AKTIV
    ) -> list:
        schluessel = (entitaet, status)
        if schluessel not in self._zeilen_cache:
            self._zeilen_cache[schluessel] = await self.repo.nach_status(entitaet, status)
        return self._zeilen_cache[schluessel]

    async def _payloads(self, entitaet: KatalogEntitaet) -> dict[str, dict]:
        return {z.schluessel: z.payload for z in await self._zeilen(entitaet)}

    async def _formeln(self) -> dict[str, Formel]:
        if self._formeln_cache is None:
            self._formeln_cache = {
                z.schluessel: Formel.model_validate({"name": z.schluessel, **z.payload})
                for z in await self._zeilen(KatalogEntitaet.FORMELN)
            }
        return self._formeln_cache

    async def _produzenten(self) -> dict[str, Formel]:
        """variable name → the Formel that produces it (`ergebnis_variable`)."""
        return {f.ergebnis_variable: f for f in (await self._formeln()).values()}

    async def _var_index(self) -> dict[str, Any]:
        """Variable definitions resolved by gruppe precedence, plus the gruppen and KONSTANTE-values
        per name (a name may be shadowed across gruppen — the grandfathered dual-gruppe case)."""
        if self._var_index_cache is not None:
            return self._var_index_cache
        defs: dict[str, VariableDefinition] = {}
        rang: dict[str, int] = {}
        gruppen: dict[str, list[str]] = {}
        konstante: dict[str, dict[str, Decimal]] = {}
        for z in await self._zeilen(KatalogEntitaet.VARIABLEN):
            name = z.schluessel
            gruppe = z.payload["gruppe"]
            rest = {k: v for k, v in z.payload.items() if k != "gruppe"}
            vardef = VariableDefinition.model_validate({"name": name, **rest})
            gruppen.setdefault(name, []).append(gruppe)
            kwert = next(
                (s.konstante for s in vardef.aufloesung if s.methode == AufloesungsMethode.KONSTANTE and s.konstante is not None),
                None,
            )
            if kwert is not None:
                konstante.setdefault(name, {})[gruppe] = kwert
            if _GRUPPE_RANG.get(gruppe, 0) >= rang.get(name, -1):
                defs[name] = vardef
                rang[name] = _GRUPPE_RANG.get(gruppe, 0)
        # The gruppe that won for each name (highest precedence present).
        primaer = {n: max(gs, key=lambda g: _GRUPPE_RANG.get(g, 0)) for n, gs in gruppen.items()}
        self._var_index_cache = {
            "defs": defs, "gruppen": gruppen, "primaer": primaer, "konstante": konstante
        }
        return self._var_index_cache

    async def _bv_vorgaenge(self) -> dict[str, list[str]]:
        """Bauverfahren code → ordered Vorgang codes (the junction of its active version)."""
        if self._bv_vorgaenge_cache is None:
            self._bv_vorgaenge_cache = {
                z.schluessel: await self.repo.vorgaenge_lesen(z.zeile_uuid)
                for z in await self._zeilen(KatalogEntitaet.BAUVERFAHREN)
            }
        return self._bv_vorgaenge_cache

    async def _leistung_bv(self) -> dict[str, list[str]]:
        if self._leistung_bv_cache is None:
            self._leistung_bv_cache = {
                z.schluessel: z.payload["bauverfahren_codes"]
                for z in await self._zeilen(KatalogEntitaet.LEISTUNG_BAUVERFAHREN)
            }
        return self._leistung_bv_cache

    async def _namen(self, entitaet: KatalogEntitaet, feld: str) -> dict[str, str]:
        return {k: p.get(feld) for k, p in (await self._payloads(entitaet)).items()}

    # --- Meta and search (T1–T3) ----------------------------------------- #
    async def katalog_uebersicht(self) -> dict[str, Any]:
        """T1: counts per entity, catalog stand (version + last change), open-draft count.

        The stand reads the katalog_stand row; on an unseeded DB (no row) it falls back to the
        max gueltig_ab across the lifecycle tables (the Phase-1 derivation)."""
        counts: dict[str, int] = {}
        letzte: Any = None
        letzter_benutzer: str | None = None
        for e in KatalogEntitaet:
            zeilen = await self._zeilen(e)
            counts[e.value] = len(zeilen)
            for z in zeilen:
                if letzte is None or z.gueltig_ab > letzte:
                    letzte, letzter_benutzer = z.gueltig_ab, z.benutzer
        stand_zeile = await self.repo.stand_lesen()
        if stand_zeile is not None:
            stand = {
                "version": stand_zeile.version,
                "aktualisiert_am": stand_zeile.aktualisiert_am,
                "benutzer": stand_zeile.benutzer,
            }
        else:
            stand = {"aktualisiert_am": letzte, "benutzer": letzter_benutzer}
        offene = await self.repo.offene_bundles()
        return _env(
            {
                "entitaeten": counts,
                "stand": stand,
                "offene_entwuerfe": len(offene),
            }
        )

    async def suche_katalog(
        self, text: str, entitaeten: list[str] | None = None, limit: int | None = None
    ) -> dict[str, Any]:
        """T2: ranked lexical (BM25) search across entities; returns (entitaet, schluessel, name, score)."""
        gewuenscht = set(entitaeten) if entitaeten else None
        dokumente: list[dict[str, Any]] = []
        for e, (name_fn, felder) in _SUCH_ENTITAETEN.items():
            if gewuenscht is not None and e.value not in gewuenscht:
                continue
            for schluessel, p in (await self._payloads(e)).items():
                text_teile = [schluessel] + [str(p.get(f)) for f in felder if p.get(f)]
                dokumente.append(
                    {
                        "entitaet": e.value,
                        "schluessel": schluessel,
                        "name": name_fn(p) or schluessel,
                        "_text": " ".join(text_teile),
                    }
                )
        ranked = _Suchindex(dokumente).score(text)
        treffer = [
            {"entitaet": d["entitaet"], "schluessel": d["schluessel"], "name": d["name"], "score": round(s, 4)}
            for d, s in ranked
        ]
        return _env(_liste(treffer, limit))

    async def zeige_dsl_funktionen(self) -> dict[str, Any]:
        """T3: the formula language — operators, comparisons, ternary, and the function whitelist."""
        funktionen = [
            {
                "name": name,
                "bedeutung": _DSL_FUNKTION_DOKU.get(name, ("(siehe Engine)",))[0],
                "beispiel": _DSL_FUNKTION_DOKU.get(name, ("", ""))[1],
            }
            for name in sorted(_FUNKTIONEN)
        ]
        return _env(
            {
                "operatoren": _DSL_OPERATOREN,
                "vergleiche": _DSL_VERGLEICHE,
                "logik": [{"symbol": "and", "bedeutung": "logisches Und"}, {"symbol": "or", "bedeutung": "logisches Oder"}],
                "bedingung": {"form": "a if bedingung else b", "bedeutung": "Ternär: a wenn Bedingung wahr, sonst b"},
                "funktionen": funktionen,
            }
        )

    # --- Leistungen (T4–T5) ---------------------------------------------- #
    async def liste_leistungen(
        self, filter_text: str | None = None, einheit: str | None = None,
        status: str = KatalogStatus.AKTIV.value, limit: int | None = None,
    ) -> dict[str, Any]:
        """T4: code, name, einheit, #Bauverfahren-Kandidaten."""
        mapping = await self._leistung_bv()
        zeilen = await self._zeilen(KatalogEntitaet.LEISTUNGEN, KatalogStatus(status))
        eintraege = [
            {
                "code": z.schluessel,
                "name": z.payload.get("name"),
                "einheit": z.payload.get("einheit"),
                "bauverfahren_kandidaten": len(mapping.get(z.schluessel, [])),
            }
            for z in zeilen
            if _passt(filter_text, z.schluessel, z.payload.get("name"))
            and (einheit is None or z.payload.get("einheit") == einheit)
        ]
        return _env(_liste(eintraege, limit))

    async def zeige_leistung(self, code: str) -> dict[str, Any]:
        """T5: full detail + ordered Bauverfahren candidates (first = default) + standard_kennung."""
        payloads = await self._payloads(KatalogEntitaet.LEISTUNGEN)
        if code not in payloads:
            return _env({"fehler": f"keine aktive Leistung mit code {code}"})
        p = payloads[code]
        bv_namen = await self._namen(KatalogEntitaet.BAUVERFAHREN, "name")
        kandidaten = [
            {"code": bv, "name": bv_namen.get(bv), "standard": i == 0}
            for i, bv in enumerate(await self._kandidaten(code))
        ]
        return _env(
            {
                "code": code,
                "name": p.get("name"),
                "beschreibung": p.get("beschreibung"),
                "standard_kennung": p.get("standard_kennung"),
                "einheit": p.get("einheit"),
                "bauverfahren": kandidaten,
            }
        )

    async def _kandidaten(self, leistung_code: str) -> list[str]:
        return (await self._leistung_bv()).get(leistung_code, [])

    # --- Bauverfahren (T6–T8) -------------------------------------------- #
    async def liste_bauverfahren(
        self, filter_text: str | None = None, status: str = KatalogStatus.AKTIV.value,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """T6: code, name, #Vorgänge, #Leistungen die es nutzen."""
        junction = await self._bv_vorgaenge()
        mapping = await self._leistung_bv()
        nutzung = Counter(bv for codes in mapping.values() for bv in codes)
        zeilen = await self._zeilen(KatalogEntitaet.BAUVERFAHREN, KatalogStatus(status))
        eintraege = [
            {
                "code": z.schluessel,
                "name": z.payload.get("name"),
                "vorgaenge": len(junction.get(z.schluessel, [])),
                "genutzt_von_leistungen": nutzung.get(z.schluessel, 0),
            }
            for z in zeilen
            if _passt(filter_text, z.schluessel, z.payload.get("name"))
        ]
        return _env(_liste(eintraege, limit))

    async def zeige_bauverfahren(self, code: str) -> dict[str, Any]:
        """T7: ordered Vorgang chain (code, name, Ausführungsart, Kostenarten) + reverse Leistungen."""
        payloads = await self._payloads(KatalogEntitaet.BAUVERFAHREN)
        if code not in payloads:
            return _env({"fehler": f"kein aktives Bauverfahren mit code {code}"})
        vorgaenge_p = await self._payloads(KatalogEntitaet.VORGAENGE)
        aa_namen = await self._namen(KatalogEntitaet.AUSFUEHRUNGSARTEN, "name")
        kette = []
        for vc in (await self._bv_vorgaenge()).get(code, []):
            vp = vorgaenge_p.get(vc, {})
            aa = vp.get("ausfuehrungsart_code")
            kette.append(
                {
                    "code": vc,
                    "name": vp.get("name"),
                    "ausfuehrungsart": {"code": aa, "name": aa_namen.get(aa)} if aa else None,
                    "kostenarten": sorted((vp.get("kostenvariablen") or {}).keys()),
                }
            )
        leistungen = [lc for lc, bvs in (await self._leistung_bv()).items() if code in bvs]
        return _env(
            {"code": code, "name": payloads[code].get("name"), "vorgaenge": kette, "genutzt_von_leistungen": leistungen}
        )

    async def finde_bauverfahren_mit_vorgang(self, vorgang_code: str) -> dict[str, Any]:
        """T8: every Bauverfahren containing the Vorgang, with its position in the chain."""
        bv_namen = await self._namen(KatalogEntitaet.BAUVERFAHREN, "name")
        treffer = []
        for bv, codes in (await self._bv_vorgaenge()).items():
            if vorgang_code in codes:
                treffer.append({"code": bv, "name": bv_namen.get(bv), "position": codes.index(vorgang_code) + 1})
        treffer.sort(key=lambda t: t["code"])
        return _env({"vorgang_code": vorgang_code, "bauverfahren": treffer, "treffer_gesamt": len(treffer)})

    # --- Vorgänge (T9–T10) ----------------------------------------------- #
    async def liste_vorgaenge(
        self, ausfuehrungsart_code: str | None = None, betriebsart_code: str | None = None,
        filter_text: str | None = None, status: str = KatalogStatus.AKTIV.value,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """T9: both machine facets as explicit filters (reverse edges of T12/T15)."""
        zeilen = await self._zeilen(KatalogEntitaet.VORGAENGE, KatalogStatus(status))
        eintraege = [
            {
                "code": z.schluessel,
                "name": z.payload.get("name"),
                "ausfuehrungsart_code": z.payload.get("ausfuehrungsart_code"),
                "betriebsart_code": z.payload.get("betriebsart_code"),
                "kostenarten": sorted((z.payload.get("kostenvariablen") or {}).keys()),
            }
            for z in zeilen
            if _passt(filter_text, z.schluessel, z.payload.get("name"))
            and (ausfuehrungsart_code is None or z.payload.get("ausfuehrungsart_code") == ausfuehrungsart_code)
            and (betriebsart_code is None or z.payload.get("betriebsart_code") == betriebsart_code)
        ]
        return _env(_liste(eintraege, limit))

    async def zeige_vorgang(self, code: str) -> dict[str, Any]:
        """T10: Ausführungsart, Betriebsart, leistung_variable, kosten_bindung, Kostenvariablen
        (each with Bezeichnung + Einheit) + reverse: containing Bauverfahren."""
        payloads = await self._payloads(KatalogEntitaet.VORGAENGE)
        if code not in payloads:
            return _env({"fehler": f"kein aktiver Vorgang mit code {code}"})
        p = payloads[code]
        aa = p.get("ausfuehrungsart_code")
        aa_namen = await self._namen(KatalogEntitaet.AUSFUEHRUNGSARTEN, "name")
        bt_namen = await self._namen(KatalogEntitaet.BETRIEBSARTEN, "bezeichnung")
        bt = p.get("betriebsart_code")
        defs = (await self._var_index())["defs"]
        kostenvariablen = [
            {
                "kostenart": ka,
                "variable": varname,
                "bezeichnung": defs[varname].bezeichnung if varname in defs else None,
                "einheit": defs[varname].einheit if varname in defs else None,
            }
            for ka, varname in (p.get("kostenvariablen") or {}).items()
        ]
        enthalten_in = [bv for bv, codes in (await self._bv_vorgaenge()).items() if code in codes]
        return _env(
            {
                "code": code,
                "name": p.get("name"),
                "ausfuehrungsart": {"code": aa, "name": aa_namen.get(aa)} if aa else None,
                "betriebsart": {"code": bt, "bezeichnung": bt_namen.get(bt)} if bt else None,
                "leistung_variable": p.get("leistung_variable"),
                "kosten_bindung": p.get("kosten_bindung") or None,
                "kostenvariablen": kostenvariablen,
                "enthalten_in_bauverfahren": enthalten_in,
            }
        )

    # --- Ausführungsarten / Betriebsarten / -kategorien (T11–T15) -------- #
    async def liste_ausfuehrungsarten(
        self, filter_text: str | None = None, status: str = KatalogStatus.AKTIV.value,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """T11: code, name, geraetebezug, #Maschinen, #Vorgänge."""
        maschinen = await self._payloads(KatalogEntitaet.MASCHINEN)
        vorgaenge = await self._payloads(KatalogEntitaet.VORGAENGE)
        n_masch = Counter(m.get("ausfuehrungsart_code") for m in maschinen.values())
        n_vorg = Counter(v.get("ausfuehrungsart_code") for v in vorgaenge.values())
        zeilen = await self._zeilen(KatalogEntitaet.AUSFUEHRUNGSARTEN, KatalogStatus(status))
        eintraege = [
            {
                "code": z.schluessel,
                "name": z.payload.get("name"),
                "geraetebezug": z.payload.get("geraetebezug"),
                "maschinen": n_masch.get(z.schluessel, 0),
                "vorgaenge": n_vorg.get(z.schluessel, 0),
            }
            for z in zeilen
            if _passt(filter_text, z.schluessel, z.payload.get("name"), z.payload.get("geraetebezug"))
        ]
        return _env(_liste(eintraege, limit))

    async def zeige_ausfuehrungsart(self, code: str) -> dict[str, Any]:
        """T12: detail + reverse both ways: machines filling this slot, Vorgänge requiring it."""
        payloads = await self._payloads(KatalogEntitaet.AUSFUEHRUNGSARTEN)
        if code not in payloads:
            return _env({"fehler": f"keine aktive Ausführungsart mit code {code}"})
        p = payloads[code]
        maschinen = [
            {"code": k, "hersteller": mp.get("hersteller"), "modell": mp.get("modell")}
            for k, mp in (await self._payloads(KatalogEntitaet.MASCHINEN)).items()
            if mp.get("ausfuehrungsart_code") == code
        ]
        vorgaenge = [
            {"code": k, "name": vp.get("name")}
            for k, vp in (await self._payloads(KatalogEntitaet.VORGAENGE)).items()
            if vp.get("ausfuehrungsart_code") == code
        ]
        return _env(
            {
                "code": code,
                "name": p.get("name"),
                "geraetebezug": p.get("geraetebezug"),
                "maschinen": maschinen,
                "vorgaenge": vorgaenge,
            }
        )

    async def liste_betriebskategorien(
        self, status: str = KatalogStatus.AKTIV.value, limit: int | None = None
    ) -> dict[str, Any]:
        """T13: each Betriebskategorie with its #Betriebsarten."""
        betriebsarten = await self._payloads(KatalogEntitaet.BETRIEBSARTEN)
        n = Counter(b.get("kategorie_code") for b in betriebsarten.values())
        zeilen = await self._zeilen(KatalogEntitaet.BETRIEBSKATEGORIEN, KatalogStatus(status))
        eintraege = [
            {"code": z.schluessel, "bezeichnung": z.payload.get("bezeichnung"), "betriebsarten": n.get(z.schluessel, 0)}
            for z in zeilen
        ]
        return _env(_liste(eintraege, limit))

    async def liste_betriebsarten(
        self, kategorie_code: str | None = None, filter_text: str | None = None,
        status: str = KatalogStatus.AKTIV.value, limit: int | None = None,
    ) -> dict[str, Any]:
        """T14: Betriebsarten, optionally scoped to one Betriebskategorie."""
        zeilen = await self._zeilen(KatalogEntitaet.BETRIEBSARTEN, KatalogStatus(status))
        eintraege = [
            {
                "code": z.schluessel,
                "bezeichnung": z.payload.get("bezeichnung"),
                "kategorie_code": z.payload.get("kategorie_code"),
                "einheit": z.payload.get("einheit"),
            }
            for z in zeilen
            if (kategorie_code is None or z.payload.get("kategorie_code") == kategorie_code)
            and _passt(filter_text, z.schluessel, z.payload.get("bezeichnung"))
        ]
        return _env(_liste(eintraege, limit))

    async def zeige_betriebsart(self, code: str) -> dict[str, Any]:
        """T15: detail + reverse: machines carrying a Leistungsprofil for it, Vorgänge selecting it."""
        payloads = await self._payloads(KatalogEntitaet.BETRIEBSARTEN)
        if code not in payloads:
            return _env({"fehler": f"keine aktive Betriebsart mit code {code}"})
        p = payloads[code]
        maschinen = [
            {"code": k, "hersteller": mp.get("hersteller"), "modell": mp.get("modell")}
            for k, mp in (await self._payloads(KatalogEntitaet.MASCHINEN)).items()
            if any(lp.get("betriebsart_code") == code for lp in (mp.get("leistungsprofile") or []))
        ]
        vorgaenge = [
            {"code": k, "name": vp.get("name")}
            for k, vp in (await self._payloads(KatalogEntitaet.VORGAENGE)).items()
            if vp.get("betriebsart_code") == code
        ]
        return _env(
            {
                "code": code,
                "bezeichnung": p.get("bezeichnung"),
                "kategorie_code": p.get("kategorie_code"),
                "einheit": p.get("einheit"),
                "beschreibung": p.get("beschreibung"),
                "maschinen": maschinen,
                "vorgaenge": vorgaenge,
            }
        )

    # --- Maschinen (T16–T17) --------------------------------------------- #
    async def liste_maschinen(
        self, ausfuehrungsart_code: str | None = None, betriebsart_code: str | None = None,
        filter_text: str | None = None, status: str = KatalogStatus.AKTIV.value,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """T16: the two facets explicit — Geräteklasse (ausfuehrungsart) and Betriebsart."""
        zeilen = await self._zeilen(KatalogEntitaet.MASCHINEN, KatalogStatus(status))
        eintraege = []
        for z in zeilen:
            p = z.payload
            profile = p.get("leistungsprofile") or []
            if ausfuehrungsart_code is not None and p.get("ausfuehrungsart_code") != ausfuehrungsart_code:
                continue
            if betriebsart_code is not None and not any(lp.get("betriebsart_code") == betriebsart_code for lp in profile):
                continue
            if not _passt(filter_text, z.schluessel, p.get("hersteller"), p.get("modell")):
                continue
            eintraege.append(
                {
                    "code": z.schluessel,
                    "hersteller": p.get("hersteller"),
                    "modell": p.get("modell"),
                    "ausfuehrungsart_code": p.get("ausfuehrungsart_code"),
                    "betriebsarten": [lp.get("betriebsart_code") for lp in profile],
                }
            )
        return _env(_liste(eintraege, limit))

    async def zeige_maschine(self, code: str) -> dict[str, Any]:
        """T17: Hersteller/Modell, slot (Ausführungsart), property bag, Leistungsprofile per Betriebsart."""
        payloads = await self._payloads(KatalogEntitaet.MASCHINEN)
        if code not in payloads:
            return _env({"fehler": f"keine aktive Maschine mit code {code}"})
        p = payloads[code]
        aa = p.get("ausfuehrungsart_code")
        aa_namen = await self._namen(KatalogEntitaet.AUSFUEHRUNGSARTEN, "name")
        eigenschaften = [
            {"schluessel": k, "wert": v.get("wert"), "einheit": v.get("einheit"), "beleg": v.get("beleg")}
            for k, v in (p.get("eigenschaften") or {}).items()
        ]
        profile = [
            {
                "betriebsart_code": lp.get("betriebsart_code"),
                "leistung": lp.get("leistung"),
                "einheit": lp.get("einheit"),
                "eigenschaften": [
                    {"schluessel": k, "wert": v.get("wert"), "einheit": v.get("einheit")}
                    for k, v in (lp.get("eigenschaften") or {}).items()
                ],
            }
            for lp in (p.get("leistungsprofile") or [])
        ]
        return _env(
            {
                "code": code,
                "hersteller": p.get("hersteller"),
                "modell": p.get("modell"),
                "ausfuehrungsart": {"code": aa, "name": aa_namen.get(aa)} if aa else None,
                "eigenschaften": eigenschaften,
                "leistungsprofile": profile,
            }
        )

    # --- Baustoffe (T18–T21) --------------------------------------------- #
    async def liste_baustoffe(
        self, kategorie: str | None = None, koernung: str | None = None,
        filter_text: str | None = None, status: str = KatalogStatus.AKTIV.value,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """T18: code, name, kategorie, koernung, einheit, basispreis."""
        zeilen = await self._zeilen(KatalogEntitaet.BAUSTOFFE, KatalogStatus(status))
        eintraege = [
            {
                "code": z.schluessel,
                "name": z.payload.get("name"),
                "kategorie": z.payload.get("kategorie"),
                "koernung": z.payload.get("koernung"),
                "einheit": z.payload.get("einheit"),
                "basispreis_eur_pro_t": z.payload.get("basispreis_eur_pro_t"),
            }
            for z in zeilen
            if _passt(filter_text, z.schluessel, z.payload.get("name"))
            and (kategorie is None or z.payload.get("kategorie") == kategorie)
            and (koernung is None or z.payload.get("koernung") == koernung)
        ]
        return _env(_liste(eintraege, limit))

    async def liste_baustoff_kategorien(self) -> dict[str, Any]:
        """T19: distinct kategorie values with counts (makes the loose vocabulary visible)."""
        zeilen = await self._payloads(KatalogEntitaet.BAUSTOFFE)
        n = Counter((p.get("kategorie") or "(ohne)") for p in zeilen.values())
        eintraege = [{"kategorie": k, "baustoffe": v} for k, v in sorted(n.items())]
        return _env({"treffer_gesamt": len(eintraege), "eintraege": eintraege})

    async def zeige_baustoff(self, code: str) -> dict[str, Any]:
        """T20: properties, base price(s), #Lieferanten carrying it, Stammdaten-Variablen bridging to it."""
        payloads = await self._payloads(KatalogEntitaet.BAUSTOFFE)
        if code not in payloads:
            return _env({"fehler": f"kein aktiver Baustoff mit code {code}"})
        p = payloads[code]
        heute = date.today()
        preise = await self.repo.preise()
        lieferanten = sorted(
            {pr.lieferant_code for pr in preise if pr.baustoff_code == code and _gueltig(pr, heute)}
        )
        brueckenvariablen = [
            {"name": name, "stammdaten_pfad": s.stammdaten_pfad}
            for name, vardef in (await self._var_index())["defs"].items()
            for s in vardef.aufloesung
            if s.methode == AufloesungsMethode.STAMMDATEN and (s.stammdaten_pfad or "").startswith("baustoff.")
        ]
        return _env(
            {
                "code": code,
                "name": p.get("name"),
                "rohdichte_t_pro_m3": p.get("rohdichte_t_pro_m3"),
                "verdichtungsfaktor": p.get("verdichtungsfaktor"),
                "koernung": p.get("koernung"),
                "kategorie": p.get("kategorie"),
                "einheit": p.get("einheit"),
                "basispreis_eur_pro_t": p.get("basispreis_eur_pro_t"),
                "basispreis_eur": p.get("basispreis_eur"),
                "lieferanten_anzahl": len(lieferanten),
                "stammdaten_variablen": brueckenvariablen,
            }
        )

    async def finde_lieferanten_fuer_baustoff(
        self, baustoff_code: str, stichtag: str | None = None
    ) -> dict[str, Any]:
        """T21: every Lieferant with a valid ex-works price at stichtag, sorted by price; location included."""
        tag = _als_datum(stichtag)
        lief_payloads = await self._payloads(KatalogEntitaet.LIEFERANTEN)
        best: dict[str, Decimal] = {}
        for pr in await self.repo.preise():
            if pr.baustoff_code == baustoff_code and _gueltig(pr, tag):
                if pr.lieferant_code not in best or pr.preis_eur_pro_t < best[pr.lieferant_code]:
                    best[pr.lieferant_code] = pr.preis_eur_pro_t
        treffer = [
            {
                "lieferant_code": lc,
                "name": lief_payloads.get(lc, {}).get("name"),
                "standort": lief_payloads.get(lc, {}).get("standort"),
                "werkspreis_eur_pro_t": preis,
            }
            for lc, preis in best.items()
        ]
        treffer.sort(key=lambda t: t["werkspreis_eur_pro_t"])
        return _env(
            {"baustoff_code": baustoff_code, "stichtag": tag, "lieferanten": treffer, "treffer_gesamt": len(treffer)}
        )

    # --- Lieferanten & Preise (T22–T24) ---------------------------------- #
    async def liste_lieferanten(
        self, filter_text: str | None = None, ort: str | None = None,
        status: str = KatalogStatus.AKTIV.value, limit: int | None = None,
    ) -> dict[str, Any]:
        """T22: code, name, Standort, #Baustoffe im Sortiment (currently valid prices)."""
        heute = date.today()
        sortiment: dict[str, set[str]] = {}
        for pr in await self.repo.preise():
            if _gueltig(pr, heute):
                sortiment.setdefault(pr.lieferant_code, set()).add(pr.baustoff_code)
        zeilen = await self._zeilen(KatalogEntitaet.LIEFERANTEN, KatalogStatus(status))
        eintraege = [
            {
                "code": z.schluessel,
                "name": z.payload.get("name"),
                "standort": z.payload.get("standort"),
                "baustoffe_im_sortiment": len(sortiment.get(z.schluessel, set())),
            }
            for z in zeilen
            if _passt(filter_text, z.schluessel, z.payload.get("name"))
            and _passt(ort, z.payload.get("standort"))
        ]
        return _env(_liste(eintraege, limit))

    async def zeige_lieferant(self, code: str) -> dict[str, Any]:
        """T23: location/coords + assortment summary grouped by Baustoff-Kategorie."""
        payloads = await self._payloads(KatalogEntitaet.LIEFERANTEN)
        if code not in payloads:
            return _env({"fehler": f"kein aktiver Lieferant mit code {code}"})
        p = payloads[code]
        heute = date.today()
        baustoffe = await self._payloads(KatalogEntitaet.BAUSTOFFE)
        kategorien: Counter[str] = Counter()
        for pr in await self.repo.preise():
            if pr.lieferant_code == code and _gueltig(pr, heute):
                kat = baustoffe.get(pr.baustoff_code, {}).get("kategorie") or "(ohne)"
                kategorien[kat] += 1
        sortiment = [{"kategorie": k, "baustoffe": v} for k, v in sorted(kategorien.items())]
        return _env(
            {
                "code": code,
                "name": p.get("name"),
                "standort": p.get("standort"),
                "breitengrad": p.get("breitengrad"),
                "laengengrad": p.get("laengengrad"),
                "sortiment": sortiment,
            }
        )

    async def zeige_preise(
        self, lieferant_code: str | None = None, baustoff_code: str | None = None,
        stichtag: str | None = None, mit_historie: bool = False,
    ) -> dict[str, Any]:
        """T24: raw price rows with validity ranges; either/both filters; mit_historie includes expired."""
        tag = _als_datum(stichtag)
        reihen = []
        for pr in await self.repo.preise():
            if lieferant_code is not None and pr.lieferant_code != lieferant_code:
                continue
            if baustoff_code is not None and pr.baustoff_code != baustoff_code:
                continue
            if not mit_historie and not _gueltig(pr, tag):
                continue
            reihen.append(
                {
                    "lieferant_code": pr.lieferant_code,
                    "baustoff_code": pr.baustoff_code,
                    "preis_eur_pro_t": pr.preis_eur_pro_t,
                    "gueltig_ab": pr.gueltig_ab,
                    "gueltig_bis": pr.gueltig_bis,
                }
            )
        reihen.sort(key=lambda r: (r["lieferant_code"], r["baustoff_code"], r["gueltig_ab"]))
        return _env({"treffer_gesamt": len(reihen), "stichtag": tag, "mit_historie": mit_historie, "eintraege": reihen})

    # --- Formeln & Variablen (T25–T30) ----------------------------------- #
    async def liste_formeln(
        self, filter_text: str | None = None, referenziert_variable: str | None = None,
        status: str = KatalogStatus.AKTIV.value, limit: int | None = None,
    ) -> dict[str, Any]:
        """T25: name, ergebnis_variable, ausdruck, einheit; referenziert_variable = reverse dep filter."""
        zeilen = await self._zeilen(KatalogEntitaet.FORMELN, KatalogStatus(status))
        eintraege = []
        for z in zeilen:
            ausdruck = z.payload.get("ausdruck", "")
            if referenziert_variable is not None and referenziert_variable not in _eingaben(ausdruck):
                continue
            if not _passt(filter_text, z.schluessel, ausdruck):
                continue
            eintraege.append(
                {
                    "name": z.schluessel,
                    "ergebnis_variable": z.payload.get("ergebnis_variable"),
                    "ausdruck": ausdruck,
                    "einheit": z.payload.get("einheit"),
                }
            )
        return _env(_liste(eintraege, limit))

    async def zeige_formel(self, name: str) -> dict[str, Any]:
        """T26: ausdruck + LaTeX + symbol legend + inputs (gruppe/Bezeichnung/Einheit) + reverse edges."""
        formeln = await self._formeln()
        if name not in formeln:
            return _env({"fehler": f"keine aktive Formel mit name {name}"})
        f = formeln[name]
        idx = await self._var_index()
        defs, primaer = idx["defs"], idx["primaer"]
        info = {
            v: VariablenLegende(
                bezeichnung=defs[v].bezeichnung if v in defs else None,
                einheit=defs[v].einheit if v in defs else None,
            )
            for v in f.eingaben()
        }
        darstellung = stelle_formel_dar(f.ausdruck, info)
        eingaben = [
            {
                "variable": v,
                "gruppe": primaer.get(v),
                "bezeichnung": defs[v].bezeichnung if v in defs else None,
                "einheit": defs[v].einheit if v in defs else None,
            }
            for v in sorted(f.eingaben())
        ]
        # Reverse edge: every Vorgang that uses the formula's output in ANY of the three variable
        # roles. The role definition is shared with verwendung_von_variable (T30) via
        # _vorgang_rollen so the detail view and the impact analysis can never disagree.
        gebunden_in = [
            vc for vc, vp in (await self._payloads(KatalogEntitaet.VORGAENGE)).items()
            if _vorgang_rollen(vp, f.ergebnis_variable)
        ]
        referenziert_in = [
            other.name for other in formeln.values()
            if other.name != name and f.ergebnis_variable in _eingaben(other.ausdruck)
        ]
        return _env(
            {
                "name": name,
                "ergebnis_variable": f.ergebnis_variable,
                "ausdruck": f.ausdruck,
                "einheit": f.einheit,
                "latex": darstellung.latex,
                "legende": [e.model_dump() for e in darstellung.legende],
                "eingaben": eingaben,
                "gebunden_in_vorgaengen": sorted(gebunden_in),
                "referenziert_in_formeln": sorted(referenziert_in),
            }
        )

    async def liste_variablen(
        self, gruppe: str | None = None, filter_text: str | None = None,
        status: str = KatalogStatus.AKTIV.value, limit: int | None = None,
    ) -> dict[str, Any]:
        """T27: name, gruppe, bezeichnung, einheit, datentyp; gruppe ∈ stammdaten|kontext|formel."""
        zeilen = await self._zeilen(KatalogEntitaet.VARIABLEN, KatalogStatus(status))
        eintraege = [
            {
                "name": z.schluessel,
                "gruppe": z.payload.get("gruppe"),
                "bezeichnung": z.payload.get("bezeichnung"),
                "einheit": z.payload.get("einheit"),
                "datentyp": z.payload.get("datentyp"),
            }
            for z in zeilen
            if (gruppe is None or z.payload.get("gruppe") == gruppe)
            and _passt(filter_text, z.schluessel, z.payload.get("bezeichnung"))
        ]
        return _env(_liste(eintraege, limit))

    async def zeige_variable(self, name: str) -> dict[str, Any]:
        """T28: definition, Einheit, Datentyp, resolution cascade, current KONSTANTE value."""
        zeilen = [z for z in await self._zeilen(KatalogEntitaet.VARIABLEN) if z.schluessel == name]
        if not zeilen:
            return _env({"fehler": f"keine aktive Variable mit name {name}"})
        zeilen.sort(key=lambda z: _GRUPPE_RANG.get(z.payload.get("gruppe"), 0), reverse=True)
        primaer = zeilen[0]

        def darstellung(z) -> dict[str, Any]:
            vardef = VariableDefinition.model_validate(
                {"name": name, **{k: v for k, v in z.payload.items() if k != "gruppe"}}
            )
            schritte = [
                {
                    "methode": s.methode,
                    "prompt": s.prompt,
                    "konfidenz_schwelle": s.konfidenz_schwelle,
                    "stammdaten_pfad": s.stammdaten_pfad,
                    "formel_name": s.formel_name,
                    "konstante": s.konstante,
                }
                for s in vardef.aufloesung
            ]
            konst = next((s.konstante for s in vardef.aufloesung if s.methode == AufloesungsMethode.KONSTANTE), None)
            return {
                "gruppe": z.payload.get("gruppe"),
                "bezeichnung": vardef.bezeichnung,
                "beschreibung": vardef.beschreibung,
                "einheit": vardef.einheit,
                "datentyp": vardef.datentyp,
                "llm_kontext": vardef.llm_kontext,
                "aufloesung": schritte,
                "konstante_wert": konst,
            }

        haupt = darstellung(primaer)
        weitere = [darstellung(z) for z in zeilen[1:]]
        return _env({"name": name, **haupt, "weitere_gruppen": weitere or None})

    async def erklaere_variable(self, name: str) -> dict[str, Any]:
        """T29: the transitive derivation tree down to KONSTANTE / STAMMDATEN / kontext leaves."""
        produzenten = await self._produzenten()
        idx = await self._var_index()
        defs, primaer = idx["defs"], idx["primaer"]

        def baum(var: str, pfad: frozenset[str]) -> dict[str, Any]:
            if var in pfad:
                return {"variable": var, "methode": "zyklus"}
            if var in produzenten:
                f = produzenten[var]
                return {
                    "variable": var,
                    "methode": "formel",
                    "formel": f.name,
                    "ausdruck": f.ausdruck,
                    "eingaben": [baum(e, pfad | {var}) for e in sorted(f.eingaben())],
                }
            vardef = defs.get(var)
            if vardef is None:
                return {"variable": var, "methode": "unbekannt"}
            for s in vardef.aufloesung:
                if s.methode == AufloesungsMethode.KONSTANTE and s.konstante is not None:
                    return {"variable": var, "methode": "konstante", "wert": s.konstante}
                if s.methode == AufloesungsMethode.STAMMDATEN:
                    return {"variable": var, "methode": "stammdaten", "stammdaten_pfad": s.stammdaten_pfad}
            return {"variable": var, "methode": "eingabe", "gruppe": primaer.get(var)}

        if name not in defs and name not in produzenten:
            return _env({"fehler": f"keine aktive Variable mit name {name}"})
        return _env(baum(name, frozenset()))

    async def verwendung_von_variable(self, name: str) -> dict[str, Any]:
        """T30: full where-used — Formeln, Vorgänge (Kostenvariable/leistung_variable/kosten_bindung),
        Globale mit ziel_variable. The impact-analysis primitive before a change."""
        formeln = [
            f.name for f in (await self._formeln()).values() if name in _eingaben(f.ausdruck)
        ]
        vorgaenge = []
        for vc, vp in (await self._payloads(KatalogEntitaet.VORGAENGE)).items():
            rollen = _vorgang_rollen(vp, name)
            if rollen:
                vorgaenge.append({"code": vc, "rollen": rollen})
        globale = [
            k for k, gp in (await self._payloads(KatalogEntitaet.GLOBALE_VARIABLEN)).items()
            if gp.get("ziel_variable") == name
        ]
        return _env(
            {
                "variable": name,
                "formeln": sorted(formeln),
                "vorgaenge": sorted(vorgaenge, key=lambda v: v["code"]),
                "globale_variablen": sorted(globale),
            }
        )

    # --- Globale Variablen (T31) ----------------------------------------- #
    async def liste_globale_variablen(self, limit: int | None = None) -> dict[str, Any]:
        """T31: the project-scoped set: name, Bezeichnung, erforderlich, ist_standort, ziel_variable, RAG."""
        zeilen = await self._zeilen(KatalogEntitaet.GLOBALE_VARIABLEN)
        eintraege = [
            {
                "name": z.schluessel,
                "bezeichnung": z.payload.get("bezeichnung"),
                "erforderlich": z.payload.get("erforderlich"),
                "ist_standort": z.payload.get("ist_standort"),
                "ziel_variable": z.payload.get("ziel_variable"),
                "rag_prompt": z.payload.get("rag_prompt"),
            }
            for z in zeilen
        ]
        return _env(_liste(eintraege, limit))

    # --- Lifecycle & Audit (T32–T33) ------------------------------------- #
    async def zeige_historie(self, entitaet: str, schluessel: str) -> dict[str, Any]:
        """T32: all versions of one entry (version, status, benutzer, gueltig_ab/bis) — the SCD-2 timeline."""
        try:
            e = KatalogEntitaet(entitaet)
        except ValueError:
            return _env({"fehler": f"unbekannte Entität: {entitaet}", "bekannt": [x.value for x in KatalogEntitaet]})
        zeilen = await self.repo.alle_versionen(e, schluessel)
        versionen = [
            {
                "version": z.version,
                "status": z.status,
                "benutzer": z.benutzer,
                "gueltig_ab": z.gueltig_ab,
                "gueltig_bis": z.gueltig_bis,
                "gruppe": z.payload.get("gruppe"),
            }
            for z in zeilen
        ]
        return _env({"entitaet": entitaet, "schluessel": schluessel, "versionen": versionen})

    async def liste_entwuerfe(self) -> dict[str, Any]:
        """T33: open draft bundles grouped by bundle, entity, and author."""
        bundles = []
        for bundle_uuid in await self.repo.offene_bundles():
            gruppen = await self.repo.nach_bundle(bundle_uuid)
            entitaeten = []
            benutzer: set[str] = set()
            for e, zeilen in gruppen.items():
                entwuerfe = [z for z in zeilen if z.status == KatalogStatus.ENTWURF]
                if not entwuerfe:
                    continue
                entitaeten.append({"entitaet": e.value, "schluessel": [z.schluessel for z in entwuerfe]})
                benutzer.update(z.benutzer for z in entwuerfe if z.benutzer)
            bundles.append(
                {"bundle_uuid": bundle_uuid, "benutzer": sorted(benutzer), "entitaeten": entitaeten}
            )
        return _env({"treffer_gesamt": len(bundles), "eintraege": bundles})


# --------------------------------------------------------------------------- #
# Module helpers
# --------------------------------------------------------------------------- #
def _vorgang_rollen(vorgang_payload: dict[str, Any], variable: str) -> list[str]:
    """The roles in which one Vorgang uses `variable` — THE single definition of "a Vorgang uses
    a variable". Both reverse-edge tools resolve through it: `zeige_formel` (T26,
    gebunden_in_vorgaengen) and `verwendung_von_variable` (T30, the impact analysis). Keeping it
    in one place is load-bearing: when the two answers disagree, a Kalkulator edits a formula on
    incomplete impact information.

    A Vorgang references variables in three distinct roles:

    - "kostenvariable" — a VALUE of `kostenvariablen` (Kostenart → variable name). These are the
      cost lines `Vorgang.kalkuliere` sums into the EKT.
    - "leistung_variable" — the productivity slot. A machine bound at Gate 4 writes its
      Leistungsprofil rate into this variable (binden.py).
    - "kosten_bindung" — a KEY of `kosten_bindung` (cost variable ← machine property-bag key).
      When a machine is bound, its property value is written into this variable and SHADOWS
      whatever the catalog would otherwise supply — a Stammdaten KONSTANTE or a Formel. This is
      the easily-missed role: for a formula-produced variable it means "in this Vorgang, a bound
      machine can override the formula", which is precisely what an author must know before
      editing that formula. No seeded Vorgang has this shape today (binding keys are currently
      all Stammdaten rates), so only the synthetic-row regression test exercises it — do not
      assume fixture coverage.
    """
    rollen: list[str] = []
    if variable in (vorgang_payload.get("kostenvariablen") or {}).values():
        rollen.append("kostenvariable")
    if vorgang_payload.get("leistung_variable") == variable:
        rollen.append("leistung_variable")
    if variable in (vorgang_payload.get("kosten_bindung") or {}):
        rollen.append("kosten_bindung")
    return rollen


def _eingaben(ausdruck: str) -> set[str]:
    """The variable names a stored formula expression references (empty on a parse error)."""
    try:
        return Formel(name="_", ergebnis_variable="_", ausdruck=ausdruck).eingaben()
    except SyntaxError:
        return set()


def _als_datum(stichtag: str | None) -> date:
    return date.fromisoformat(stichtag) if stichtag else date.today()


def _gueltig(preis: Any, tag: date) -> bool:
    return preis.gueltig_ab <= tag and (preis.gueltig_bis is None or tag <= preis.gueltig_bis)
