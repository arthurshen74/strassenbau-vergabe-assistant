from __future__ import annotations

from decimal import Decimal

import httpx
import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

import shared.clients.maps.geo as geo
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
    route_polyline,
)
from shared.config import settings

ADDRESS = "L 101 bei Nordhausen, Deutschland"
SITE: Koordinate = (Decimal("51.42"), Decimal("10.81"))
SUPPLIER_A: Koordinate = (Decimal("51.503"), Decimal("10.792"))   # LIEF_001 Nordhausen
SUPPLIER_B: Koordinate = (Decimal("52.265"), Decimal("10.527"))   # LIEF_051 Braunschweig (far)


def _client_with_handler(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _capture_spans(monkeypatch) -> InMemorySpanExporter:
    """Route the maps client's tracer to an in-memory exporter (isolated from the global
    provider) so a test can assert on the emitted spans."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(geo, "_tracer", provider.get_tracer("test"))
    return exporter


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


async def test_geocode_error_surfaces_google_message(monkeypatch) -> None:
    monkeypatch.setattr(settings, "calculator_mock", False)
    monkeypatch.setattr(settings, "google_static_maps_api_key", "test-key")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "status": "REQUEST_DENIED",
            "error_message": "You must enable Billing on the Google Cloud Project.",
            "results": [],
        })

    # The bare status alone doesn't say why; Google's error_message must reach the raised error.
    with pytest.raises(MapsError, match="You must enable Billing"):
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


async def test_route_polyline_mock_is_haversine_no_line(monkeypatch) -> None:
    monkeypatch.setattr(settings, "calculator_mock", True)
    km, polyline = await route_polyline(SUPPLIER_A, SITE)
    assert km == _haversine_km(SUPPLIER_A, SITE)
    assert polyline == ""                          # empty -> the map draws a straight segment


async def test_route_polyline_live_parses_distance_and_polyline(monkeypatch) -> None:
    monkeypatch.setattr(settings, "calculator_mock", False)
    monkeypatch.setattr(settings, "google_static_maps_api_key", "test-key")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers[HEADER_API_KEY] == "test-key"
        return httpx.Response(200, json={
            "routes": [{"distanceMeters": 12500, "polyline": {"encodedPolyline": "abc123"}}],
        })

    km, polyline = await route_polyline(SUPPLIER_A, SITE, client=_client_with_handler(handler))
    assert km == Decimal("12.5")
    assert polyline == "abc123"


async def test_geocode_emits_span(monkeypatch) -> None:
    monkeypatch.setattr(settings, "calculator_mock", True)
    spans = _capture_spans(monkeypatch)

    await geocode(ADDRESS)

    span = spans.get_finished_spans()[0]
    assert span.name == geo.SPAN_GEOCODE
    assert span.status.status_code == StatusCode.UNSET       # success leaves status unset
    assert span.attributes[geo.ATTR_ADDRESS] == ADDRESS
    assert span.attributes[geo.ATTR_MOCK] is True
    assert span.attributes[geo.ATTR_KONFIDENZ] == 1.0
    assert span.attributes[geo.ATTR_BREITENGRAD] == float(MOCK_BAUSTELLE_LAT)
    assert span.attributes[geo.ATTR_LAENGENGRAD] == float(MOCK_BAUSTELLE_LON)


async def test_geocode_span_records_error(monkeypatch) -> None:
    monkeypatch.setattr(settings, "calculator_mock", False)
    monkeypatch.setattr(settings, "google_static_maps_api_key", None)
    spans = _capture_spans(monkeypatch)

    with pytest.raises(MapsError):
        await geocode(ADDRESS)

    span = spans.get_finished_spans()[0]
    assert span.name == geo.SPAN_GEOCODE
    assert span.status.status_code == StatusCode.ERROR


async def test_route_matrix_span_counts_routed_and_fallback(monkeypatch) -> None:
    monkeypatch.setattr(settings, "calculator_mock", False)
    monkeypatch.setattr(settings, "google_static_maps_api_key", "test-key")
    spans = _capture_spans(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        # First pair routes; the second has no route -> haversine fallback for that pair.
        return httpx.Response(200, json=[
            {"originIndex": 0, "destinationIndex": 0, "distanceMeters": 12500, "condition": "ROUTE_EXISTS"},
            {"originIndex": 1, "destinationIndex": 0, "condition": "ROUTE_NOT_FOUND"},
        ])

    await route_matrix([SUPPLIER_A, SUPPLIER_B], [SITE], client=_client_with_handler(handler))

    span = spans.get_finished_spans()[0]
    assert span.name == geo.SPAN_ROUTE_MATRIX
    assert span.attributes[geo.ATTR_ORIGIN_COUNT] == 2
    assert span.attributes[geo.ATTR_DEST_COUNT] == 1
    assert span.attributes[geo.ATTR_MOCK] is False
    assert span.attributes[geo.ATTR_ROUTED_PAIRS] == 1
    assert span.attributes[geo.ATTR_FALLBACK_PAIRS] == 1


async def test_route_matrix_span_records_error(monkeypatch) -> None:
    monkeypatch.setattr(settings, "calculator_mock", False)
    monkeypatch.setattr(settings, "google_static_maps_api_key", "test-key")
    spans = _capture_spans(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    with pytest.raises(MapsError):
        await route_matrix([SUPPLIER_A], [SITE], client=_client_with_handler(handler))

    span = spans.get_finished_spans()[0]
    assert span.name == geo.SPAN_ROUTE_MATRIX
    assert span.status.status_code == StatusCode.ERROR
