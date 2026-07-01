"""Supplier ranking for the EKT calculator (async, I/O at the edge).

Given a Baustoff and the Baustelle coordinate, rank the suppliers that carry the material by
DELIVERED price (ex-works price + transport x road distance). Road distance comes from the Routes
API via the maps client; to bound cost/quota we pre-filter to the N nearest carriers by great-circle
distance and route-matrix only those (ARCHITECTURE §5; LIEFERANTENWAHL_PLAN §6.5).

This is the live, async counterpart to the offline `materialien.guenstigster_lieferant` (sync,
haversine-only) baseline, which stays as the deterministic mock/test reference.
"""

from __future__ import annotations

from decimal import Decimal

import httpx
from pydantic import BaseModel, ConfigDict

from shared.clients.maps.geo import Koordinate, route_matrix
from shared.config import settings
from shared.services.kalkulation_v2.lieferanten import LIEFERANTEN, haversine_km
from shared.services.kalkulation_v2.materialien import (
    BAUSTOFFE,
    STICHTAG,
    TRANSPORT_EUR_PRO_T_KM,
)

DEFAULT_TOP_N = 10

# Road distances are reported to 0.1 km (matches the maps client + guenstigster_lieferant rounding).
KM_QUANT = Decimal("0.1")


class LieferantAngebot(BaseModel):
    """One ranked supplier offer for a material at the Baustelle: ex-works price, road distance,
    and the delivered (frei Baustelle) price the ranking sorts on."""
    model_config = ConfigDict(extra="forbid")

    code: str
    name: str
    ort: str
    werk_eur_pro_t: Decimal
    strasse_km: Decimal
    frei_bau_eur_pro_t: Decimal


class LieferantenRangliste(BaseModel):
    """Ranked supplier offers plus an optional warning. `warnung` is set only when no carrier is
    within the configured radius and the ranking fell back to the single nearest one."""
    model_config = ConfigDict(extra="forbid")

    angebote: list[LieferantAngebot]
    warnung: str | None = None


def _ort(standort: str | None) -> str:
    """Town from the supplier `standort` ('Straße, PLZ Ort, Deutschland'); the PLZ is dropped."""
    if not standort:
        return ""
    teile = standort.split(", ")
    return teile[1].split(" ", 1)[-1] if len(teile) > 1 else standort


async def rang_lieferanten(
    baustoff_code: str,
    breitengrad: Decimal,
    laengengrad: Decimal,
    *,
    top_n: int = DEFAULT_TOP_N,
    client: httpx.AsyncClient | None = None,
) -> LieferantenRangliste:
    """Suppliers carrying `baustoff_code`, ranked cheapest-delivered first. Carriers beyond the
    configured radius are dropped before routing; if that leaves none, the ranking falls back to
    the single nearest carrier and sets `warnung`. Empty `angebote` when no supplier carries the
    material at all (the caller then falls back to the catalog base price)."""
    baustoff = BAUSTOFFE.get(baustoff_code)
    if baustoff is None:
        return LieferantenRangliste(angebote=[])

    # Carriers: a valid ex-works price for this material at the Stichtag, with a known location.
    carriers: list[tuple[float, object, Decimal]] = []
    for lief in LIEFERANTEN.values():
        werk = lief.preis_fuer(baustoff.id, STICHTAG)
        if werk is None or lief.breitengrad is None or lief.laengengrad is None:
            continue
        luft = haversine_km(float(lief.breitengrad), float(lief.laengengrad),
                            float(breitengrad), float(laengengrad))
        carriers.append((luft, lief, werk))
    if not carriers:
        return LieferantenRangliste(angebote=[])

    # Soft radius filter: route only carriers within the radius; if none qualify, fall back to the
    # single nearest one (regardless of distance) and warn. Pre-sort by great-circle distance.
    carriers.sort(key=lambda t: t[0])
    radius = settings.calculator_lieferant_radius_km
    im_radius = [c for c in carriers if c[0] <= radius]
    kein_lieferant_im_radius = not im_radius
    nahe = im_radius[:top_n] if im_radius else carriers[:1]

    origins: list[Koordinate] = [(l.breitengrad, l.laengengrad) for _, l, _ in nahe]  # type: ignore[attr-defined]
    matrix = await route_matrix(origins, [(breitengrad, laengengrad)], client=client)

    # Coarse HGV approximation: Google can only DRIVE-route, so scale the road distance by a
    # configurable detour factor (1.0 = no adjustment).
    faktor = Decimal(str(settings.calculator_hgv_detour_factor))
    angebote = [
        LieferantAngebot(
            code=lief.code, name=lief.name, ort=_ort(lief.standort),  # type: ignore[attr-defined]
            werk_eur_pro_t=werk, strasse_km=(zeile[0] * faktor).quantize(KM_QUANT),
            frei_bau_eur_pro_t=(werk + TRANSPORT_EUR_PRO_T_KM * (zeile[0] * faktor)).quantize(
                Decimal("0.01")),
        )
        for (_, lief, werk), zeile in zip(nahe, matrix)
    ]
    angebote.sort(key=lambda a: a.frei_bau_eur_pro_t)

    warnung = None
    if kein_lieferant_im_radius and angebote:
        nearest = angebote[0]
        warnung = (f"Kein Lieferant innerhalb {radius:g} km für {baustoff_code} — "
                   f"nächster ist {nearest.name} ({nearest.strasse_km} km).")
    return LieferantenRangliste(angebote=angebote, warnung=warnung)
