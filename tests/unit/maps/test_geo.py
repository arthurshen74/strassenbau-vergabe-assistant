from __future__ import annotations

from decimal import Decimal

import httpx
import pytest

from shared.clients.maps.geo import (
    HEADER_API_KEY,
    HEADER_FIELD_MASK,
    MOCK_BAUSTELLE_LAT,
    MOCK_BAUSTELLE_LON,
    GeocodeResult,
    Koordinate,
    MapsError,
    _haversine_km,
    geocode,
    road_distance_km,
    route_matrix,
)
from shared.config import settings

ADDRESS = "L 101 bei Nordhausen, Deutschland"
SITE: Koordinate = (Decimal("51.42"), Decimal("10.81"))
SUPPLIER_A: Koordinate = (Decimal("51.503"), Decimal("10.792"))   # LIEF_001 Nordhausen
SUPPLIER_B: Koordinate = (Decimal("52.265"), Decimal("10.527"))   # LIEF_051 Braunschweig (far)


def _client_with_handler(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_geocode_mock_returns_fixture_site(monkeypatch) -> None:
    monkeypatch.setattr(settings, "calculator_mock", True)
    res = await geocode(ADDRESS)
    assert res == GeocodeResult(breitengrad=MOCK_BAUSTELLE_LAT, laengengrad=MOCK_BAUSTELLE_LON,
                                formatiert=ADDRESS, konfidenz=1.0)


async def test_geocode_live_parses_location_and_confidence(monkeypatch) -> None:
    monkeypatch.setattr(settings, "calculator_mock", False)
    monkeypatch.setattr(settings, "google_static_maps_api_key", "test-key")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["address"] == ADDRESS
        assert request.url.params["key"] == "test-key"
        return httpx.Response(200, json={
            "status": "OK",
            "results": [{
                "geometry": {"location": {"lat": 51.5, "lng": 10.79}, "location_type": "ROOFTOP"},
                "formatted_address": "Nordhausen, Deutschland",
            }],
        })

    res = await geocode(ADDRESS, client=_client_with_handler(handler))
    assert res.breitengrad == Decimal("51.5")
    assert res.laengengrad == Decimal("10.79")
    assert res.konfidenz == 1.0
    assert res.formatiert == "Nordhausen, Deutschland"


async def test_geocode_raises_without_key(monkeypatch) -> None:
    monkeypatch.setattr(settings, "calculator_mock", False)
    monkeypatch.setattr(settings, "google_static_maps_api_key", None)
    with pytest.raises(MapsError):
        await geocode(ADDRESS)


async def test_geocode_raises_on_zero_results(monkeypatch) -> None:
    monkeypatch.setattr(settings, "calculator_mock", False)
    monkeypatch.setattr(settings, "google_static_maps_api_key", "test-key")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "ZERO_RESULTS", "results": []})

    with pytest.raises(MapsError):
        await geocode(ADDRESS, client=_client_with_handler(handler))


async def test_route_matrix_mock_uses_haversine(monkeypatch) -> None:
    monkeypatch.setattr(settings, "calculator_mock", True)
    grid = await route_matrix([SUPPLIER_A, SUPPLIER_B], [SITE])
    assert grid == [[_haversine_km(SUPPLIER_A, SITE)], [_haversine_km(SUPPLIER_B, SITE)]]


async def test_route_matrix_live_parses_and_falls_back(monkeypatch) -> None:
    monkeypatch.setattr(settings, "calculator_mock", False)
    monkeypatch.setattr(settings, "google_static_maps_api_key", "test-key")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers[HEADER_API_KEY] == "test-key"
        assert request.headers[HEADER_FIELD_MASK]
        # A routed first pair; the second has no route -> the grid keeps the haversine fallback.
        return httpx.Response(200, json=[
            {"originIndex": 0, "destinationIndex": 0, "distanceMeters": 12500, "condition": "ROUTE_EXISTS"},
            {"originIndex": 1, "destinationIndex": 0, "condition": "ROUTE_NOT_FOUND"},
        ])

    grid = await route_matrix([SUPPLIER_A, SUPPLIER_B], [SITE], client=_client_with_handler(handler))
    assert grid[0][0] == Decimal("12.5")                       # 12500 m -> 12.5 km
    assert grid[1][0] == _haversine_km(SUPPLIER_B, SITE)       # missing route -> haversine fallback


async def test_route_matrix_wraps_http_error(monkeypatch) -> None:
    monkeypatch.setattr(settings, "calculator_mock", False)
    monkeypatch.setattr(settings, "google_static_maps_api_key", "test-key")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    with pytest.raises(MapsError):
        await route_matrix([SUPPLIER_A], [SITE], client=_client_with_handler(handler))


async def test_road_distance_km_mock(monkeypatch) -> None:
    monkeypatch.setattr(settings, "calculator_mock", True)
    assert await road_distance_km(SUPPLIER_A, SITE) == _haversine_km(SUPPLIER_A, SITE)
