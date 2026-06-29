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
from shared.services.kalkulation_v2.lieferanten import LIEFERANTEN, haversine_km
from shared.services.kalkulation_v2.materialien import (
    BAUSTOFFE,
    STICHTAG,
    TRANSPORT_EUR_PRO_T_KM,
)

DEFAULT_TOP_N = 10


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
) -> list[LieferantAngebot]:
    """Suppliers carrying `baustoff_code`, ranked cheapest-delivered first. Empty when no supplier
    carries the material (the caller then falls back to the catalog base price)."""
    baustoff = BAUSTOFFE.get(baustoff_code)
    if baustoff is None:
        return []

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
        return []

    # Pre-filter to the N nearest by great-circle distance before paying for road routing.
    carriers.sort(key=lambda t: t[0])
    nahe = carriers[:top_n]
    origins: list[Koordinate] = [(l.breitengrad, l.laengengrad) for _, l, _ in nahe]  # type: ignore[attr-defined]
    matrix = await route_matrix(origins, [(breitengrad, laengengrad)], client=client)

    angebote = [
        LieferantAngebot(
            code=lief.code, name=lief.name, ort=_ort(lief.standort),  # type: ignore[attr-defined]
            werk_eur_pro_t=werk, strasse_km=zeile[0],
            frei_bau_eur_pro_t=(werk + TRANSPORT_EUR_PRO_T_KM * zeile[0]).quantize(Decimal("0.01")),
        )
        for (_, lief, werk), zeile in zip(nahe, matrix)
    ]
    angebote.sort(key=lambda a: a.frei_bau_eur_pro_t)
    return angebote
