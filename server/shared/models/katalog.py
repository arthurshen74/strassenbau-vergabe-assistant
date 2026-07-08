"""Domain models for the persisted `kalkulation_v2` catalog (the Katalog Store).

The catalog lives in Postgres with a draft/active lifecycle: `KatalogStatus` names the
three states, `KatalogEntitaet` the persisted entity types, and `VariablenGruppe` the three
variable sources the fixtures split across (so the provider can rebuild them exactly).
`KatalogZeile` is the generic CRUD envelope — lifecycle metadata plus the entity's payload
as a plain dict — used uniformly by the one generic repository. `KatalogPreis` is one supplier
price row (the non-lifecycle price history). The payload contracts themselves stay the existing
`kalkulation_v2.model` classes; there are no parallel DTOs.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from shared.services.kalkulation_v2.model import (
    Ausführungsart,
    Baustoff,
    Betriebsart,
    Betriebskategorie,
    Formel,
    Leistung,
    Maschine,
    VariableDefinition,
    VorgangRechnung,
)


class KatalogStatus(StrEnum):
    """Lifecycle state of a catalog row. The single source for these values.

    `verworfen` and `archiviert` are distinct ends: a discarded draft was never in force, a
    superseded version was. Only activation writes `archiviert`."""

    ENTWURF = "entwurf"
    AKTIV = "aktiv"
    VERWORFEN = "verworfen"
    ARCHIVIERT = "archiviert"


class KatalogEntitaet(StrEnum):
    """The persisted lifecycle catalog entities (one table each, `katalog_<value>`)."""

    LEISTUNGEN = "leistungen"
    BAUVERFAHREN = "bauverfahren"
    VORGAENGE = "vorgaenge"
    AUSFUEHRUNGSARTEN = "ausfuehrungsarten"
    BETRIEBSKATEGORIEN = "betriebskategorien"
    BETRIEBSARTEN = "betriebsarten"
    FORMELN = "formeln"
    VARIABLEN = "variablen"
    GLOBALE_VARIABLEN = "globale_variablen"
    BAUSTOFFE = "baustoffe"
    LIEFERANTEN = "lieferanten"
    MASCHINEN = "maschinen"
    LEISTUNG_BAUVERFAHREN = "leistung_bauverfahren"


class VariablenGruppe(StrEnum):
    """The fixture sources of `katalog_variablen`, preserved so the provider can rebuild
    STAMMDATEN_VARIABLEN / KONTEXT_VARIABLEN and their KATALOG merge exactly. FORMEL is
    retired (Formeln are no variables any more) but still parses the pre-migration rows;
    the provider refuses to load them."""

    STAMMDATEN = "stammdaten"
    KONTEXT = "kontext"
    FORMEL = "formel"


class KatalogZeile(BaseModel):
    """One catalog row in envelope form: lifecycle metadata + the entity payload as a dict.

    `schluessel` is the natural key value (a `code`, or a `name` for Formeln/Variablen);
    `payload` holds the remaining entity columns (JSONB payloads already parsed to dict/list).
    The provider merges `{key_field: schluessel, **payload}` and validates that into the
    matching `kalkulation_v2.model` class.
    """

    model_config = ConfigDict(extra="forbid")

    zeile_uuid: UUID
    schluessel: str
    version: int
    status: KatalogStatus
    bundle_uuid: UUID | None = None
    benutzer: str | None = None
    gueltig_ab: datetime
    gueltig_bis: datetime | None = None
    payload: dict[str, Any]


class KatalogPreis(BaseModel):
    """One supplier price row (`katalog_lieferanten_preise`): version-independent, immutable VALUE.

    References a Lieferant and a Baustoff by code; a price correction inserts a new row rather
    than updating. Maps field-for-field onto `BaustoffPreis` (plus the owning `lieferant_code`).
    Phase 2 adds a lifecycle `status` (+ `bundle_uuid`/`benutzer`) so a price rides the
    draft→confirm flow like everything else — the VALUE stays immutable/unversioned; the status
    only tracks entwurf|aktiv|verworfen (D5). A superseded price stays `aktiv` with a closed
    domain-time `gueltig_bis`, so `archiviert` never occurs on prices."""

    model_config = ConfigDict(extra="forbid")

    lieferant_code: str
    baustoff_code: str
    preis_eur_pro_t: Decimal
    gueltig_ab: date
    gueltig_bis: date | None = None
    status: KatalogStatus = KatalogStatus.AKTIV
    bundle_uuid: UUID | None = None
    benutzer: str | None = None


class KatalogStandZeile(BaseModel):
    """The global catalog version row (`katalog_stand`, single row id=1): the effective catalog's
    `version` (bumped on activation) plus the last-touched audit (`aktualisiert_am`/`benutzer`)."""

    model_config = ConfigDict(extra="forbid")

    version: int
    aktualisiert_am: datetime
    benutzer: str | None = None


# --------------------------------------------------------------------------- #
# Katalog bundle (the write unit) — flat, code-referenced transport shapes.
# --------------------------------------------------------------------------- #
class BundleVorgang(BaseModel):
    """A Vorgang in bundle transport: the Ausführungsart is referenced by code (embedded on load),
    matching the table payload directly (the domain `Vorgang` embeds the object instead). The
    cost computation travels as the `rechnung` instantiation dict (base formula bindings)."""

    model_config = ConfigDict(extra="forbid")

    code: str
    name: str
    ausfuehrungsart_code: str | None = None
    betriebsart_code: str | None = None
    leistung_instanz: str | None = None
    kosten_bindung: dict[str, str] = Field(default_factory=dict)
    rechnung: VorgangRechnung = Field(default_factory=VorgangRechnung)


class BundleBauverfahren(BaseModel):
    """A Bauverfahren in bundle transport: its Vorgänge are an ordered list of codes (the junction),
    not embedded objects (first entry runs first)."""

    model_config = ConfigDict(extra="forbid")

    code: str
    name: str
    vorgang_codes: list[str] = Field(default_factory=list)


class BundleLieferant(BaseModel):
    """A Lieferant in bundle transport (D6): code + location. Its price rows travel separately as
    `BundlePreis` (prices are immutable value rows, not part of the Lieferant's payload)."""

    model_config = ConfigDict(extra="forbid")

    code: str
    name: str
    standort: str | None = None
    breitengrad: Decimal | None = None
    laengengrad: Decimal | None = None


class BundlePreis(BaseModel):
    """A supplier price in bundle transport (D6): references a Lieferant and a Baustoff by code.
    Saved as a draft price row; on activation it closes out an overlapping open-ended predecessor
    (D5). `gueltig_ab` defaults are applied at the tool layer (today)."""

    model_config = ConfigDict(extra="forbid")

    lieferant_code: str
    baustoff_code: str
    preis_eur_pro_t: Decimal
    gueltig_ab: date
    gueltig_bis: date | None = None


class BundleVariable(BaseModel):
    """A managed variable plus the gruppe it belongs to. FORMEL-gruppe variables are derived from
    the bundle's Formeln (like the `formel()` fixture helper), so this list carries stammdaten/
    kontext variables; an explicit formel-gruppe entry is allowed and wins over the derived one."""

    model_config = ConfigDict(extra="forbid")

    gruppe: VariablenGruppe
    definition: VariableDefinition


class KatalogBundle(BaseModel):
    """One coherent catalog change set — THE catalog write unit: any subset of entities that
    belong together, validated as a whole, persisted as drafts sharing a bundle_uuid, and
    activated atomically. A single superseded rate is a bundle; a full recipe (Leistung +
    Bauverfahren + Vorgänge + Formeln) is just the most complex kind. Lieferanten and Preise
    join the field set in Phase 2 (KATALOG_AGENT_PHASE2_PLAN.md D6); project globals stay out
    (governed set)."""

    model_config = ConfigDict(extra="forbid")

    leistungen: list[Leistung] = Field(default_factory=list)
    bauverfahren: list[BundleBauverfahren] = Field(default_factory=list)
    vorgaenge: list[BundleVorgang] = Field(default_factory=list)
    ausfuehrungsarten: list[Ausführungsart] = Field(default_factory=list)
    betriebskategorien: list[Betriebskategorie] = Field(default_factory=list)
    betriebsarten: list[Betriebsart] = Field(default_factory=list)
    formeln: list[Formel] = Field(default_factory=list)
    variablen: list[BundleVariable] = Field(default_factory=list)
    baustoffe: list[Baustoff] = Field(default_factory=list)
    maschinen: list[Maschine] = Field(default_factory=list)
    lieferanten: list[BundleLieferant] = Field(default_factory=list)
    preise: list[BundlePreis] = Field(default_factory=list)
    leistung_bauverfahren: dict[str, list[str]] = Field(default_factory=dict)


class BundleBericht(BaseModel):
    """Validation report for a bundle: hard errors block save/activation; supersede flags note the
    bundle keys that update (rather than create) an active catalog row."""

    model_config = ConfigDict(extra="forbid")

    fehler: list[str] = Field(default_factory=list)
    aktualisierungen: list[str] = Field(default_factory=list)

    @property
    def gueltig(self) -> bool:
        return not self.fehler


class BundleZustand(StrEnum):
    """The confirm card's view of a bundle: still open for a decision, already activated,
    discarded without ever being active, or activated and later superseded."""

    OFFEN = "offen"
    AKTIVIERT = "aktiviert"
    VERWORFEN = "verworfen"
    GESCHLOSSEN = "geschlossen"


class BundleZeileAnsicht(BaseModel):
    """One row of a bundle for the confirm card's state re-query (entity, natural key, status)."""

    model_config = ConfigDict(extra="forbid")

    entitaet: str
    schluessel: str
    status: KatalogStatus


class BundleZustandAnsicht(BaseModel):
    """The GET /katalog/bundle/{uuid} payload: the bundle's derived state + its rows. Lets a card
    re-query on reload so a draft long since activated or discarded renders truthfully."""

    model_config = ConfigDict(extra="forbid")

    zustand: BundleZustand
    zeilen: list[BundleZeileAnsicht]
