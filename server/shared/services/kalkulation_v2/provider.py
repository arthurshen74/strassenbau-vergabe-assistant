"""KatalogProvider — load the persisted catalog into the engine's module-level dicts.

At runtime the DB is the source of truth: `lade_katalog` reads every `aktiv` row, validates it
into the existing `kalkulation_v2.model` classes, and refills the module dicts IN PLACE
(`d.clear(); d.update(...)`) so every importer that holds a reference (`graph.py`, `binden.py`,
`lieferant_ranking.py`, `worklist.py`, `project_context/*`) sees the new data. It is idempotent —
called at API startup and again after a bundle activation. A process that never calls it (unit
tests, `store.py __main__`) keeps running on the fixture data unchanged.

Load order respects embedding dependencies (Ausführungsart → Vorgang → Bauverfahren; the three
variable groups → KATALOG). After the dicts, the derived state that is computed at import time
from them is rebuilt: `store.KATALOG`, the Baustoff BM25 index, and the two globals sets.

Scope note: catalog-layer derived state is rebuilt here. The calculator's `graph.py` computes its
label spaces and gate payloads (leistung_index(), bauverfahren_ressourcen(), …) per use from the
module dicts, and the engine path used for calculation (`kalkuliere_kontext`) reads the refilled
dicts directly — so a newly activated entry is classifiable, pickable and calculable immediately.

Two reconstruction subtleties are handled explicitly: Ausführungsarten and Vorgänge are keyed by
`code` (the fixtures key them by short names that the engine never reads by key — it iterates
`.values()`), and Maschine property values are re-coerced to Decimal (a numeric value round-trips
through JSONB as a string; `binden.py` binds a machine cost only when the value `isinstance` Decimal).
"""

from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy.ext.asyncio import AsyncConnection

from shared.models.katalog import KatalogEntitaet, KatalogZeile, VariablenGruppe
from shared.repositories.katalog import KatalogRepository
from shared.services.kalkulation_v2 import ausfuehrungsarten as m_aa
from shared.services.kalkulation_v2 import baustoff_suche as m_bs
from shared.services.kalkulation_v2 import bauverfahren as m_bv
from shared.services.kalkulation_v2 import betriebsarten as m_bt
from shared.services.kalkulation_v2 import formel as m_formel
from shared.services.kalkulation_v2 import globale_variablen as m_glob
from shared.services.kalkulation_v2 import kontext_variablen as m_kontext
from shared.services.kalkulation_v2 import leistung_bauverfahren as m_lb
from shared.services.kalkulation_v2 import leistungen as m_leist
from shared.services.kalkulation_v2 import lieferanten as m_lief
from shared.services.kalkulation_v2 import maschinen as m_masch
from shared.services.kalkulation_v2 import materialien as m_mat
from shared.services.kalkulation_v2 import stammdaten as m_stamm
from shared.services.kalkulation_v2 import store as m_store
from shared.services.kalkulation_v2 import vorgaenge as m_vorg
from shared.services.kalkulation_v2.globale_variablen import GlobaleVariable
from shared.services.kalkulation_v2.model import (
    Ausführungsart,
    Baustoff,
    BaustoffPreis,
    Baustofflieferant,
    Bauverfahren,
    Betriebsart,
    Betriebskategorie,
    Formel,
    Leistung,
    Maschine,
    VariableDefinition,
    Vorgang,
    VorgangRechnung,
)

logger = logging.getLogger(__name__)


def _refill(ziel: dict, neu: dict) -> None:
    """Replace a module dict's contents in place so every importer sees the new data."""
    ziel.clear()
    ziel.update(neu)


def _validate(zeile: KatalogZeile, model_cls, schluessel_feld: str):
    """Merge the natural key back under its model field and validate the payload."""
    return model_cls.model_validate({schluessel_feld: zeile.schluessel, **zeile.payload})


def _wert_zu_decimal(wert: Any) -> Any:
    """A numeric MaschinenWert value round-trips through JSONB as a string; restore the Decimal
    so `binden.py` (which binds a machine cost only for Decimal values) behaves as with fixtures."""
    if isinstance(wert, str):
        try:
            return Decimal(wert)
        except InvalidOperation:
            return wert
    return wert


def _maschine_aus_zeile(zeile: KatalogZeile) -> Maschine:
    def norm_bag(bag: dict) -> dict:
        return {k: {**v, "wert": _wert_zu_decimal(v.get("wert"))} for k, v in bag.items()}

    payload = dict(zeile.payload)
    payload["eigenschaften"] = norm_bag(payload["eigenschaften"])
    payload["leistungsprofile"] = [
        {**lp, "eigenschaften": norm_bag(lp.get("eigenschaften", {}))}
        for lp in payload["leistungsprofile"]
    ]
    return Maschine.model_validate({"code": zeile.schluessel, **payload})


async def lade_katalog(conn: AsyncConnection) -> dict[str, int] | None:
    """Load all `aktiv` rows, validate into domain models, refill the module dicts in place and
    rebuild derived state. Returns a per-entity count summary of what was loaded. If the katalog
    tables are empty, keep the fixture data (dev DB without seed must not crash), warn once and
    return None."""
    repo = KatalogRepository(conn)
    if await repo.ist_leer():
        logger.warning("katalog_* tables are empty — keeping kalkulation_v2 fixture data.")
        return None

    async def aktive(entitaet: KatalogEntitaet) -> list[KatalogZeile]:
        return await repo.aktive(entitaet)

    # 1) Betriebskategorien + Betriebsarten
    _refill(
        m_bt.BETRIEBSKATEGORIEN,
        {z.schluessel: _validate(z, Betriebskategorie, "code") for z in await aktive(KatalogEntitaet.BETRIEBSKATEGORIEN)},
    )
    _refill(
        m_bt.BETRIEBSARTEN,
        {z.schluessel: _validate(z, Betriebsart, "code") for z in await aktive(KatalogEntitaet.BETRIEBSARTEN)},
    )

    # 2) Ausführungsarten — keyed by code (see module docstring).
    _refill(
        m_aa.AUSFUEHRUNGSARTEN,
        {z.schluessel: _validate(z, Ausführungsart, "code") for z in await aktive(KatalogEntitaet.AUSFUEHRUNGSARTEN)},
    )

    # 3) Basisformeln + Variablen (split by gruppe into the two fixture dicts).
    _refill(
        m_formel.FORMELN,
        {z.schluessel: _validate(z, Formel, "name") for z in await aktive(KatalogEntitaet.FORMELN)},
    )
    stammdaten_var: dict[str, VariableDefinition] = {}
    kontext_var: dict[str, VariableDefinition] = {}
    ziel = {
        VariablenGruppe.STAMMDATEN: stammdaten_var,
        VariablenGruppe.KONTEXT: kontext_var,
    }
    for z in await aktive(KatalogEntitaet.VARIABLEN):
        gruppe = VariablenGruppe(z.payload["gruppe"])
        if gruppe not in ziel:
            raise ValueError(f"katalog_variablen: Gruppe '{gruppe}' wird nicht mehr geladen "
                             f"(Variable {z.schluessel}) — Formeln sind keine Variablen mehr.")
        rest = {k: v for k, v in z.payload.items() if k != "gruppe"}
        ziel[gruppe][z.schluessel] = VariableDefinition.model_validate({"name": z.schluessel, **rest})
    _refill(m_stamm.STAMMDATEN_VARIABLEN, stammdaten_var)
    _refill(m_kontext.KONTEXT_VARIABLEN, kontext_var)

    # 4) Baustoffe
    _refill(
        m_mat.BAUSTOFFE,
        {z.schluessel: _validate(z, Baustoff, "code") for z in await aktive(KatalogEntitaet.BAUSTOFFE)},
    )

    # 5) Lieferanten + prices (BaustoffPreis attached field-for-field).
    preise_je_lieferant: dict[str, list[BaustoffPreis]] = {}
    for p in await repo.preise():
        preise_je_lieferant.setdefault(p.lieferant_code, []).append(
            BaustoffPreis(
                baustoff_code=p.baustoff_code,
                preis_eur_pro_t=p.preis_eur_pro_t,
                gueltig_ab=p.gueltig_ab,
                gueltig_bis=p.gueltig_bis,
            )
        )
    lieferanten: dict[str, Baustofflieferant] = {}
    for z in await aktive(KatalogEntitaet.LIEFERANTEN):
        lief = _validate(z, Baustofflieferant, "code")
        lief.preise = preise_je_lieferant.get(z.schluessel, [])
        lieferanten[z.schluessel] = lief
    _refill(m_lief.LIEFERANTEN, lieferanten)

    # 6) Maschinen (numeric property values restored to Decimal).
    _refill(
        m_masch.MASCHINEN,
        {z.schluessel: _maschine_aus_zeile(z) for z in await aktive(KatalogEntitaet.MASCHINEN)},
    )

    # 7) Vorgänge — embed the loaded Ausführungsart by code; keyed by code.
    vorgaenge: dict[str, Vorgang] = {}
    for z in await aktive(KatalogEntitaet.VORGAENGE):
        p = z.payload
        aa_code = p["ausfuehrungsart_code"]
        vorgaenge[z.schluessel] = Vorgang(
            code=z.schluessel,
            name=p["name"],
            ausfuehrungsart=m_aa.AUSFUEHRUNGSARTEN.get(aa_code) if aa_code else None,
            betriebsart_code=p["betriebsart_code"],
            leistung_instanz=p["leistung_instanz"],
            kosten_bindung=p["kosten_bindung"],
            rechnung=VorgangRechnung.model_validate(p["rechnung"]),
        )
    _refill(m_vorg.VORGAENGE, vorgaenge)

    # 8) Bauverfahren — embed loaded Vorgang instances ordered by the junction.
    bauverfahren: dict[str, Bauverfahren] = {}
    for z in await aktive(KatalogEntitaet.BAUVERFAHREN):
        codes = await repo.vorgaenge_lesen(z.zeile_uuid)
        bauverfahren[z.schluessel] = Bauverfahren(
            code=z.schluessel,
            name=z.payload["name"],
            vorgaenge=[vorgaenge[c] for c in codes],
        )
    _refill(m_bv.BAUVERFAHREN, bauverfahren)

    # 9) Leistungen + Leistung→Bauverfahren mapping.
    _refill(
        m_leist.LEISTUNGEN,
        {z.schluessel: _validate(z, Leistung, "code") for z in await aktive(KatalogEntitaet.LEISTUNGEN)},
    )
    _refill(
        m_lb.LEISTUNG_BAUVERFAHREN,
        {z.schluessel: z.payload["bauverfahren_codes"] for z in await aktive(KatalogEntitaet.LEISTUNG_BAUVERFAHREN)},
    )

    # 10) Globale Variablen
    _refill(
        m_glob.GLOBALE_VARIABLEN,
        {z.schluessel: _validate(z, GlobaleVariable, "name") for z in await aktive(KatalogEntitaet.GLOBALE_VARIABLEN)},
    )

    # Derived state rebuilt from the refilled dicts (mirrors the fixtures' import-time derivation).
    _refill(m_store.KATALOG, {**m_stamm.STAMMDATEN_VARIABLEN, **m_kontext.KONTEXT_VARIABLEN})
    m_bs.baue_index()
    m_glob.GLOBAL_VAR_NAMES.clear()
    m_glob.GLOBAL_VAR_NAMES.update(m_glob.GLOBALE_VARIABLEN)
    m_glob.ERFORDERLICHE_GLOBALE.clear()
    m_glob.ERFORDERLICHE_GLOBALE.update(
        n for n, gv in m_glob.GLOBALE_VARIABLEN.items() if gv.erforderlich
    )

    summary = {
        KatalogEntitaet.BETRIEBSKATEGORIEN.value: len(m_bt.BETRIEBSKATEGORIEN),
        KatalogEntitaet.BETRIEBSARTEN.value: len(m_bt.BETRIEBSARTEN),
        KatalogEntitaet.AUSFUEHRUNGSARTEN.value: len(m_aa.AUSFUEHRUNGSARTEN),
        KatalogEntitaet.FORMELN.value: len(m_formel.FORMELN),
        KatalogEntitaet.VARIABLEN.value: len(m_store.KATALOG),
        KatalogEntitaet.GLOBALE_VARIABLEN.value: len(m_glob.GLOBALE_VARIABLEN),
        KatalogEntitaet.BAUSTOFFE.value: len(m_mat.BAUSTOFFE),
        KatalogEntitaet.LIEFERANTEN.value: len(m_lief.LIEFERANTEN),
        "lieferanten_preise": sum(len(l.preise) for l in m_lief.LIEFERANTEN.values()),
        KatalogEntitaet.MASCHINEN.value: len(m_masch.MASCHINEN),
        KatalogEntitaet.VORGAENGE.value: len(m_vorg.VORGAENGE),
        KatalogEntitaet.BAUVERFAHREN.value: len(m_bv.BAUVERFAHREN),
        KatalogEntitaet.LEISTUNGEN.value: len(m_leist.LEISTUNGEN),
        KatalogEntitaet.LEISTUNG_BAUVERFAHREN.value: len(m_lb.LEISTUNG_BAUVERFAHREN),
    }
    # Provenance: report the effective catalog version so neu-laden surfaces it.
    stand_zeile = await repo.stand_lesen()
    if stand_zeile is not None:
        summary["stand"] = stand_zeile.version
    return summary
