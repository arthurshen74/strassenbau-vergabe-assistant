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
    angebote = await rang_lieferanten("FSS_0_32", *SITE)
    assert angebote, "FSS 0/32 is widely carried -> non-empty ranking"
    frei = [a.frei_bau_eur_pro_t for a in angebote]
    assert frei == sorted(frei)                                  # cheapest delivered first
    assert all(isinstance(a, LieferantAngebot) for a in angebote)


async def test_top_offer_matches_offline_baseline() -> None:
    # In mock mode the async ranker and the sync haversine baseline use the same distance,
    # transport rate and Stichtag, so their cheapest-delivered supplier agrees.
    top = (await rang_lieferanten("FSS_0_32", *SITE))[0]
    lief, _werk, _km, frei = guenstigster_lieferant("FSS_0_32", float(SITE[0]), float(SITE[1]))[0]
    assert top.code == lief.code
    assert top.frei_bau_eur_pro_t == frei


async def test_top_n_caps_routed_candidates() -> None:
    angebote = await rang_lieferanten("FSS_0_32", *SITE, top_n=3)
    assert len(angebote) <= 3


async def test_uncarried_material_returns_empty() -> None:
    # No supplier price rows exist for the joint-sealant specialty -> caller falls back to catalog.
    assert await rang_lieferanten("FUGENMASSE_N2", *SITE) == []


async def test_unknown_material_returns_empty() -> None:
    assert await rang_lieferanten("DOES_NOT_EXIST", *SITE) == []
