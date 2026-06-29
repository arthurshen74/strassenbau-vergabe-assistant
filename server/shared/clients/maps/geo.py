"""Google Geocoding + Routes client for the EKT calculator.

Two I/O capabilities the pure calc engine must not own (ARCHITECTURE §1): geocoding the
Baubeschreibung to a Baustelle coordinate, and routing supplier -> Baustelle road distances.
`geocode` wraps the Geocoding API; `route_matrix` wraps the Routes API computeRouteMatrix so one
call ranks N candidate suppliers. Both reuse `settings.google_static_maps_api_key` (the shared
Google Maps Platform key).

Mock mode (`settings.calculator_mock`) returns deterministic stubs with no network: geocode
yields a fixed fixture coordinate, distances fall back to the haversine helper (x1.3 detour) so
the whole offline calculator flow stays runnable (graph.py mock-mode contract). The live Routes
path also falls back to haversine per origin/destination pair when a route is missing, so a gap in
Google's coverage degrades the ranking instead of crashing it.
"""

from __future__ import annotations

import logging
from decimal import Decimal

import httpx
from pydantic import BaseModel, ConfigDict

from shared.config import settings
from shared.services.kalkulation_v2.lieferanten import haversine_km

logger = logging.getLogger(__name__)

# (Breitengrad, Längengrad) in decimal degrees.
Koordinate = tuple[Decimal, Decimal]

# Mock-mode fixture site: the demo Baustelle on the L 101 near Nordhausen (lieferanten.py __main__).
MOCK_BAUSTELLE_LAT = Decimal("51.42")
MOCK_BAUSTELLE_LON = Decimal("10.81")

# Haversine -> road-distance detour factor; matches lieferanten.entfernung_km.
DETOUR_FACTOR = Decimal("1.3")

# --- Geocoding API contract (request params + response keys) ---
GEOCODE_PARAM_ADDRESS = "address"
GEOCODE_PARAM_KEY = "key"
GEOCODE_KEY_STATUS = "status"
GEOCODE_KEY_RESULTS = "results"
GEOCODE_KEY_GEOMETRY = "geometry"
GEOCODE_KEY_LOCATION = "location"
GEOCODE_KEY_LAT = "lat"
GEOCODE_KEY_LNG = "lng"
GEOCODE_KEY_LOCATION_TYPE = "location_type"
GEOCODE_KEY_FORMATTED = "formatted_address"
GEOCODE_KEY_PARTIAL = "partial_match"
GEOCODE_STATUS_OK = "OK"

# Geocoder location_type -> confidence (precise rooftop down to a town-level approximation).
GEOCODE_CONFIDENCE: dict[str, float] = {
    "ROOFTOP": 1.0,
    "RANGE_INTERPOLATED": 0.8,
    "GEOMETRIC_CENTER": 0.6,
    "APPROXIMATE": 0.4,
}
GEOCODE_CONFIDENCE_DEFAULT = 0.5

# --- Routes API computeRouteMatrix contract (headers, request + response keys) ---
HEADER_API_KEY = "X-Goog-Api-Key"
HEADER_FIELD_MASK = "X-Goog-FieldMask"
ROUTES_FIELD_MASK = "originIndex,destinationIndex,distanceMeters,condition"
ROUTES_KEY_ORIGINS = "origins"
ROUTES_KEY_DESTINATIONS = "destinations"
ROUTES_KEY_WAYPOINT = "waypoint"
ROUTES_KEY_LOCATION = "location"
ROUTES_KEY_LATLNG = "latLng"
ROUTES_KEY_LATITUDE = "latitude"
ROUTES_KEY_LONGITUDE = "longitude"
ROUTES_KEY_TRAVEL_MODE = "travelMode"
ROUTES_KEY_ROUTING_PREFERENCE = "routingPreference"
ROUTES_TRAVEL_MODE_DRIVE = "DRIVE"
ROUTES_ROUTING_PREFERENCE = "TRAFFIC_UNAWARE"
ROUTES_KEY_ORIGIN_INDEX = "originIndex"
ROUTES_KEY_DEST_INDEX = "destinationIndex"
ROUTES_KEY_DISTANCE_METERS = "distanceMeters"
ROUTES_KEY_CONDITION = "condition"
ROUTES_CONDITION_OK = "ROUTE_EXISTS"

# Distances are reported to 0.1 km (matches guenstigster_lieferant rounding).
KM_QUANT = Decimal("0.1")


class MapsError(Exception):
    """Raised when a live geocode/route request cannot be completed (missing key or failure)."""


class GeocodeResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    breitengrad: Decimal
    laengengrad: Decimal
    formatiert: str
    konfidenz: float


def _haversine_km(origin: Koordinate, dest: Koordinate) -> Decimal:
    """Great-circle distance x detour factor, as a Decimal km (the offline distance baseline)."""
    km = haversine_km(float(origin[0]), float(origin[1]), float(dest[0]), float(dest[1]))
    return (Decimal(str(km)) * DETOUR_FACTOR).quantize(KM_QUANT)


async def geocode(address: str, *, client: httpx.AsyncClient | None = None) -> GeocodeResult:
    """Resolve an address/place string to a Baustelle coordinate. Mock mode returns the fixture
    site; live mode calls the Geocoding API and raises MapsError on a missing key or no result."""
    if settings.calculator_mock:
        return GeocodeResult(breitengrad=MOCK_BAUSTELLE_LAT, laengengrad=MOCK_BAUSTELLE_LON,
                             formatiert=address, konfidenz=1.0)
    if not settings.google_static_maps_api_key:
        raise MapsError("google_static_maps_api_key is not configured")

    params = {GEOCODE_PARAM_ADDRESS: address, GEOCODE_PARAM_KEY: settings.google_static_maps_api_key}
    owns = client is None
    http = client or httpx.AsyncClient(timeout=settings.maps_request_timeout_seconds)
    try:
        response = await http.get(settings.google_maps_geocoding_url, params=params)
        response.raise_for_status()
        body = response.json()
    except httpx.HTTPError as exc:
        logger.exception("Geocoding request failed for address=%s", address)
        raise MapsError(str(exc)) from exc
    finally:
        if owns:
            await http.aclose()

    results = body.get(GEOCODE_KEY_RESULTS) or []
    if body.get(GEOCODE_KEY_STATUS) != GEOCODE_STATUS_OK or not results:
        raise MapsError(f"geocode returned no result for {address!r} (status {body.get(GEOCODE_KEY_STATUS)})")
    top = results[0]
    loc = top[GEOCODE_KEY_GEOMETRY][GEOCODE_KEY_LOCATION]
    konfidenz = GEOCODE_CONFIDENCE.get(
        top[GEOCODE_KEY_GEOMETRY].get(GEOCODE_KEY_LOCATION_TYPE), GEOCODE_CONFIDENCE_DEFAULT)
    if top.get(GEOCODE_KEY_PARTIAL):                 # a partial match is inherently less certain
        konfidenz = min(konfidenz, 0.5)
    return GeocodeResult(
        breitengrad=Decimal(str(loc[GEOCODE_KEY_LAT])),
        laengengrad=Decimal(str(loc[GEOCODE_KEY_LNG])),
        formatiert=top.get(GEOCODE_KEY_FORMATTED, address),
        konfidenz=konfidenz)


def _waypoint(coord: Koordinate) -> dict:
    return {ROUTES_KEY_WAYPOINT: {ROUTES_KEY_LOCATION: {ROUTES_KEY_LATLNG: {
        ROUTES_KEY_LATITUDE: float(coord[0]), ROUTES_KEY_LONGITUDE: float(coord[1])}}}}


async def route_matrix(origins: list[Koordinate], dests: list[Koordinate], *,
                       client: httpx.AsyncClient | None = None) -> list[list[Decimal]]:
    """Road distance (km) for every origin x destination pair. Mock mode and any pair Google
    cannot route fall back to haversine, so the result is always a full grid (never None)."""
    if not origins or not dests:
        return [[] for _ in origins]
    haversine_grid = [[_haversine_km(o, d) for d in dests] for o in origins]
    if settings.calculator_mock:
        return haversine_grid
    if not settings.google_static_maps_api_key:
        raise MapsError("google_static_maps_api_key is not configured")

    headers = {HEADER_API_KEY: settings.google_static_maps_api_key, HEADER_FIELD_MASK: ROUTES_FIELD_MASK}
    payload = {
        ROUTES_KEY_ORIGINS: [_waypoint(o) for o in origins],
        ROUTES_KEY_DESTINATIONS: [_waypoint(d) for d in dests],
        ROUTES_KEY_TRAVEL_MODE: ROUTES_TRAVEL_MODE_DRIVE,
        ROUTES_KEY_ROUTING_PREFERENCE: ROUTES_ROUTING_PREFERENCE,
    }
    owns = client is None
    http = client or httpx.AsyncClient(timeout=settings.maps_request_timeout_seconds)
    try:
        response = await http.post(settings.google_maps_route_matrix_url, headers=headers, json=payload)
        response.raise_for_status()
        elements = response.json()
    except httpx.HTTPError as exc:
        logger.exception("Route matrix request failed (%d origins, %d dests)", len(origins), len(dests))
        raise MapsError(str(exc)) from exc
    finally:
        if owns:
            await http.aclose()

    # computeRouteMatrix returns a flat, possibly out-of-order list keyed by origin/dest index;
    # start from the haversine grid and overwrite each pair that routed successfully.
    grid = haversine_grid
    for el in elements:
        if el.get(ROUTES_KEY_CONDITION) != ROUTES_CONDITION_OK or ROUTES_KEY_DISTANCE_METERS not in el:
            continue
        i, j = el[ROUTES_KEY_ORIGIN_INDEX], el[ROUTES_KEY_DEST_INDEX]
        grid[i][j] = (Decimal(el[ROUTES_KEY_DISTANCE_METERS]) / 1000).quantize(KM_QUANT)
    return grid


async def road_distance_km(origin: Koordinate, dest: Koordinate, *,
                           client: httpx.AsyncClient | None = None) -> Decimal:
    """Road distance (km) between two coordinates."""
    return (await route_matrix([origin], [dest], client=client))[0][0]
