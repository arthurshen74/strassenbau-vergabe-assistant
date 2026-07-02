from __future__ import annotations

from decimal import Decimal

import pytest

from shared.config import settings
from shared.services.calculator.lieferant_ranking import LieferantAngebot, rang_lieferanten
from shared.services.kalkulation_v2.lieferanten import LIEFERANTEN
from shared.services.kalkulation_v2.lieferanten_preise import lade_preise
from shared.services.kalkulation_v2.materialien import BAUSTOFFE, guenstigster_lieferant

# Demo Baustelle on the L 101 near Nordhausen (matches the mock geocode fixture).
SITE = (Decimal("51.42"), Decimal("10.81"))


@pytest.fixture(autouse=True)
def _mock_and_prices(monkeypatch) -> None:
    # Mock mode makes route_matrix use haversine (no network); the static price list must be
    # attached to LIEFERANTEN (store.py does this at app assembly).
    monkeypatch.setattr(settings, "calculator_mock", True)
    lade_preise(BAUSTOFFE, LIEFERANTEN)


async def test_ranks_cheapest_delivered_first_and_sorted() -> None:
    rangliste = await rang_lieferanten("FSS_0_32", *SITE)
    assert rangliste.angebote, "FSS 0/32 is widely carried -> non-empty ranking"
    assert rangliste.warnung is None                            # carriers exist within the radius
    frei = [a.frei_bau_eur_pro_t for a in rangliste.angebote]
    assert frei == sorted(frei)                                 # cheapest delivered first
    assert all(isinstance(a, LieferantAngebot) for a in rangliste.angebote)


async def test_top_offer_matches_offline_baseline() -> None:
    # In mock mode the async ranker and the sync haversine baseline use the same distance,
    # transport rate and Stichtag, so their cheapest-delivered supplier agrees.
    top = (await rang_lieferanten("FSS_0_32", *SITE)).angebote[0]
    lief, _werk, _km, frei = guenstigster_lieferant("FSS_0_32", float(SITE[0]), float(SITE[1]))[0]
    assert top.code == lief.code
    assert top.frei_bau_eur_pro_t == frei


async def test_top_n_caps_routed_candidates() -> None:
    rangliste = await rang_lieferanten("FSS_0_32", *SITE, top_n=3)
    assert len(rangliste.angebote) <= 3


async def test_no_supplier_in_radius_falls_back_to_nearest_with_warning(monkeypatch) -> None:
    # A sub-metre radius excludes every carrier -> fall back to the single nearest one + warn.
    monkeypatch.setattr(settings, "calculator_lieferant_radius_km", 0.001)
    rangliste = await rang_lieferanten("FSS_0_32", *SITE)
    assert len(rangliste.angebote) == 1
    assert rangliste.warnung is not None
    assert "Kein Lieferant innerhalb" in rangliste.warnung


async def test_hgv_detour_factor_scales_distance(monkeypatch) -> None:
    monkeypatch.setattr(settings, "calculator_hgv_detour_factor", 1.0)
    base = (await rang_lieferanten("FSS_0_32", *SITE, top_n=1)).angebote[0]
    monkeypatch.setattr(settings, "calculator_hgv_detour_factor", 2.0)
    scaled = (await rang_lieferanten("FSS_0_32", *SITE, top_n=1)).angebote[0]
    # The same nearest carrier, its road distance scaled by the detour factor.
    assert scaled.code == base.code
    assert scaled.strasse_km == base.strasse_km * 2


async def test_uncarried_material_returns_empty() -> None:
    # Per-m2 surface treatments are not gap-filled (the delivered-EUR/t model does not apply), so
    # no supplier carries them -> the caller falls back to the catalog per-unit price.
    rangliste = await rang_lieferanten("DSK_5", *SITE)
    assert rangliste.angebote == []
    assert rangliste.warnung is None


async def test_unknown_material_returns_empty() -> None:
    rangliste = await rang_lieferanten("DOES_NOT_EXIST", *SITE)
    assert rangliste.angebote == []
