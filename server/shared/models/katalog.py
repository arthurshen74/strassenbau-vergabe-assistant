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
    Kostenart,
    Leistung,
    Maschine,
    VariableDefinition,
)


class KatalogStatus(StrEnum):
    """Lifecycle state of a catalog row. The single source for these values."""

    ENTWURF = "entwurf"
    AKTIV = "aktiv"
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
    """The three fixture sources of `katalog_variablen`, preserved so the provider can rebuild
    STAMMDATEN_VARIABLEN / KONTEXT_VARIABLEN / FORMEL_VARIABLEN and their KATALOG merge exactly."""

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
    """One supplier price row (`katalog_lieferanten_preise`): version-independent, immutable.

    References a Lieferant and a Baustoff by code; a price correction inserts a new row rather
    than updating. Maps field-for-field onto `BaustoffPreis` (plus the owning `lieferant_code`)."""

    model_config = ConfigDict(extra="forbid")

    lieferant_code: str
    baustoff_code: str
    preis_eur_pro_t: Decimal
    gueltig_ab: date
    gueltig_bis: date | None = None


# --------------------------------------------------------------------------- #
# Katalog bundle (the write unit) — flat, code-referenced transport shapes.
# --------------------------------------------------------------------------- #
class BundleVorgang(BaseModel):
    """A Vorgang in bundle transport: the Ausführungsart is referenced by code (embedded on load),
    matching the table payload directly (the domain `Vorgang` embeds the object instead)."""

    model_config = ConfigDict(extra="forbid")

    code: str
    name: str
    ausfuehrungsart_code: str | None = None
    betriebsart_code: str | None = None
    leistung_variable: str | None = None
    kosten_bindung: dict[str, str] = Field(default_factory=dict)
    kostenvariablen: dict[Kostenart, str] = Field(default_factory=dict)


class BundleBauverfahren(BaseModel):
    """A Bauverfahren in bundle transport: its Vorgänge are an ordered list of codes (the junction),
    not embedded objects (first entry runs first)."""

    model_config = ConfigDict(extra="forbid")

    code: str
    name: str
    vorgang_codes: list[str] = Field(default_factory=list)


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
