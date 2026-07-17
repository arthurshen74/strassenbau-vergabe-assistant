"""Google Geocoding + Routes client for the EKT calculator.

Two I/O capabilities the pure calc engine must not own (ARCHITECTURE §1): geocoding the
Baubeschreibung to a Baustelle coordinate, and routing supplier -> Baustelle road
distances. `geocode` wraps the Geocoding API; `route_matrix` wraps the Routes API
computeRouteMatrix so one call ranks N candidate suppliers. Both reuse
`settings.google_static_maps_api_key` (the shared Google Maps Platform key).

Mock mode (`settings.calculator_mock`) returns deterministic stubs with no network:
geocode yields a fixed fixture coordinate, distances fall back to the haversine helper
(x1.3 detour) so the whole offline calculator flow stays runnable (graph.py mock-mode
contract). The live Routes path also falls back to haversine per origin/destination pair
when a route is missing, so a gap in Google's coverage degrades the ranking instead of
crashing it.
"""

from __future__ import annotations

import logging
from decimal import Decimal

import httpx
from opentelemetry import trace
from opentelemetry.trace import Span
from pydantic import BaseModel, ConfigDict

from shared.config import settings
from shared.services.kalkulation_v2.lieferanten import haversine_km

logger = logging.getLogger(__name__)
_tracer = trace.get_tracer(__name__)

# (Breitengrad, Längengrad) in decimal degrees.
Koordinate = tuple[Decimal, Decimal]

# Mock-mode fixture site: the demo Baustelle on the L 101 near Nordhausen
# (lieferanten.py __main__).
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
GEOCODE_KEY_ERROR_MESSAGE = (
    "error_message"  # Google's human reason on non-OK (billing/referrer/etc.)
)
GEOCODE_STATUS_OK = "OK"

# Geocoder location_type -> confidence (precise rooftop down to a town-level
# approximation).
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

# --- Routes API computeRoutes contract (single route, for the road polyline) ---
COMPUTE_FIELD_MASK = "routes.distanceMeters,routes.polyline.encodedPolyline"
COMPUTE_KEY_ORIGIN = "origin"
COMPUTE_KEY_DESTINATION = "destination"
COMPUTE_KEY_ROUTES = "routes"
COMPUTE_KEY_POLYLINE = "polyline"
COMPUTE_KEY_ENCODED = "encodedPolyline"

# Distances are reported to 0.1 km (matches guenstigster_lieferant rounding).
KM_QUANT = Decimal("0.1")

# --- OTel span names + attribute keys (Phoenix observability labels) ---
SPAN_GEOCODE = "maps.geocode"
SPAN_ROUTE_MATRIX = "maps.route_matrix"
ATTR_ADDRESS = "maps.address"
ATTR_MOCK = "maps.mock"
ATTR_KONFIDENZ = "maps.konfidenz"
ATTR_BREITENGRAD = "maps.breitengrad"
ATTR_LAENGENGRAD = "maps.laengengrad"
ATTR_FORMATIERT = "maps.formatiert"
ATTR_ORIGIN_COUNT = "maps.origin_count"
ATTR_DEST_COUNT = "maps.dest_count"
ATTR_ROUTED_PAIRS = "maps.routed_pairs"
ATTR_FALLBACK_PAIRS = "maps.haversine_fallback_pairs"


class MapsError(Exception):
    """Raised when a live geocode/route request cannot be completed (missing key or
    failure)."""


class GeocodeResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    breitengrad: Decimal
    laengengrad: Decimal
    formatiert: str
    konfidenz: float


def _haversine_km(origin: Koordinate, dest: Koordinate) -> Decimal:
    """Great-circle distance x detour factor, as a Decimal km (the offline distance
    baseline)."""
    km = haversine_km(
        float(origin[0]), float(origin[1]), float(dest[0]), float(dest[1])
    )
    return (Decimal(str(km)) * DETOUR_FACTOR).quantize(KM_QUANT)


def _record_geocode(span: Span, result: GeocodeResult) -> None:
    """Stamp the resolved coordinate + confidence onto the geocode span."""
    span.set_attribute(ATTR_KONFIDENZ, result.konfidenz)
    span.set_attribute(ATTR_BREITENGRAD, float(result.breitengrad))
    span.set_attribute(ATTR_LAENGENGRAD, float(result.laengengrad))
    span.set_attribute(ATTR_FORMATIERT, result.formatiert)


async def geocode(
    address: str, *, client: httpx.AsyncClient | None = None
) -> GeocodeResult:
    """Resolve an address/place string to a Baustelle coordinate. Mock mode returns the
    fixture site; live mode calls the Geocoding API and raises MapsError on a missing
    key or no result. Emits a `maps.geocode` span (address in, coordinate + confidence
    out; ERROR on failure)."""
    with _tracer.start_as_current_span(SPAN_GEOCODE) as span:
        span.set_attribute(ATTR_ADDRESS, address)
        span.set_attribute(ATTR_MOCK, settings.calculator_mock)
        if settings.calculator_mock:
            result = GeocodeResult(
                breitengrad=MOCK_BAUSTELLE_LAT,
                laengengrad=MOCK_BAUSTELLE_LON,
                formatiert=address,
                konfidenz=1.0,
            )
            _record_geocode(span, result)
            return result
        if not settings.google_static_maps_api_key:
            raise MapsError("google_static_maps_api_key is not configured")

        params = {
            GEOCODE_PARAM_ADDRESS: address,
            GEOCODE_PARAM_KEY: settings.google_static_maps_api_key,
        }
        owns = client is None
        http = client or httpx.AsyncClient(
            timeout=settings.maps_request_timeout_seconds
        )
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
            # Google returns a human `error_message` on REQUEST_DENIED/OVER_QUERY_LIMIT
            # (billing, key restriction, API not enabled, ...); surface it so the cause
            # isn't a bare status.
            grund = body.get(GEOCODE_KEY_ERROR_MESSAGE)
            detail = f" — {grund}" if grund else ""
            raise MapsError(
                f"geocode returned no result for {address!r} "
                f"(status {body.get(GEOCODE_KEY_STATUS)}){detail}"
            )
        top = results[0]
        loc = top[GEOCODE_KEY_GEOMETRY][GEOCODE_KEY_LOCATION]
        konfidenz = GEOCODE_CONFIDENCE.get(
            top[GEOCODE_KEY_GEOMETRY].get(GEOCODE_KEY_LOCATION_TYPE),
            GEOCODE_CONFIDENCE_DEFAULT,
        )
        if top.get(GEOCODE_KEY_PARTIAL):  # a partial match is inherently less certain
            konfidenz = min(konfidenz, 0.5)
        result = GeocodeResult(
            breitengrad=Decimal(str(loc[GEOCODE_KEY_LAT])),
            laengengrad=Decimal(str(loc[GEOCODE_KEY_LNG])),
            formatiert=top.get(GEOCODE_KEY_FORMATTED, address),
            konfidenz=konfidenz,
        )
        _record_geocode(span, result)
        return result


def _location(coord: Koordinate) -> dict:
    return {
        ROUTES_KEY_LOCATION: {
            ROUTES_KEY_LATLNG: {
                ROUTES_KEY_LATITUDE: float(coord[0]),
                ROUTES_KEY_LONGITUDE: float(coord[1]),
            }
        }
    }


def _waypoint(coord: Koordinate) -> dict:  # computeRouteMatrix wraps a location
    return {ROUTES_KEY_WAYPOINT: _location(coord)}


async def route_matrix(
    origins: list[Koordinate],
    dests: list[Koordinate],
    *,
    client: httpx.AsyncClient | None = None,
) -> list[list[Decimal]]:
    """Road distance (km) for every origin x destination pair. Mock mode and any pair
    Google cannot route fall back to haversine, so the result is always a full grid
    (never None). Emits a `maps.route_matrix` span (origin/destination counts + how many
    pairs were road-routed vs fell back to haversine; ERROR on failure)."""
    if not origins or not dests:
        return [[] for _ in origins]
    with _tracer.start_as_current_span(SPAN_ROUTE_MATRIX) as span:
        span.set_attribute(ATTR_ORIGIN_COUNT, len(origins))
        span.set_attribute(ATTR_DEST_COUNT, len(dests))
        span.set_attribute(ATTR_MOCK, settings.calculator_mock)
        gesamt_paare = len(origins) * len(dests)
        haversine_grid = [[_haversine_km(o, d) for d in dests] for o in origins]
        if settings.calculator_mock:
            span.set_attribute(ATTR_ROUTED_PAIRS, 0)
            span.set_attribute(ATTR_FALLBACK_PAIRS, gesamt_paare)
            return haversine_grid
        if not settings.google_static_maps_api_key:
            raise MapsError("google_static_maps_api_key is not configured")

        headers = {
            HEADER_API_KEY: settings.google_static_maps_api_key,
            HEADER_FIELD_MASK: ROUTES_FIELD_MASK,
        }
        payload = {
            ROUTES_KEY_ORIGINS: [_waypoint(o) for o in origins],
            ROUTES_KEY_DESTINATIONS: [_waypoint(d) for d in dests],
            ROUTES_KEY_TRAVEL_MODE: ROUTES_TRAVEL_MODE_DRIVE,
            ROUTES_KEY_ROUTING_PREFERENCE: ROUTES_ROUTING_PREFERENCE,
        }
        owns = client is None
        http = client or httpx.AsyncClient(
            timeout=settings.maps_request_timeout_seconds
        )
        try:
            response = await http.post(
                settings.google_maps_route_matrix_url, headers=headers, json=payload
            )
            response.raise_for_status()
            elements = response.json()
        except httpx.HTTPError as exc:
            logger.exception(
                "Route matrix request failed (%d origins, %d dests)",
                len(origins),
                len(dests),
            )
            # The Routes API returns its reason in the error response body (billing, key
            # restriction, API not enabled); include it so the cause isn't just the HTTP
            # status.
            koerper = getattr(getattr(exc, "response", None), "text", "") or ""
            detail = f" — {koerper[:500]}" if koerper else ""
            raise MapsError(f"{exc}{detail}") from exc
        finally:
            if owns:
                await http.aclose()

        # computeRouteMatrix returns a flat, possibly out-of-order list keyed by
        # origin/dest index; start from the haversine grid and overwrite each pair that
        # routed successfully.
        grid = haversine_grid
        geroutet = 0
        for el in elements:
            if (
                el.get(ROUTES_KEY_CONDITION) != ROUTES_CONDITION_OK
                or ROUTES_KEY_DISTANCE_METERS not in el
            ):
                continue
            i, j = el[ROUTES_KEY_ORIGIN_INDEX], el[ROUTES_KEY_DEST_INDEX]
            grid[i][j] = (Decimal(el[ROUTES_KEY_DISTANCE_METERS]) / 1000).quantize(
                KM_QUANT
            )
            geroutet += 1
        span.set_attribute(ATTR_ROUTED_PAIRS, geroutet)
        span.set_attribute(ATTR_FALLBACK_PAIRS, gesamt_paare - geroutet)
        return grid


async def road_distance_km(
    origin: Koordinate, dest: Koordinate, *, client: httpx.AsyncClient | None = None
) -> Decimal:
    """Road distance (km) between two coordinates."""
    return (await route_matrix([origin], [dest], client=client))[0][0]


async def route_polyline(
    origin: Koordinate, dest: Koordinate, *, client: httpx.AsyncClient | None = None
) -> tuple[Decimal, str]:
    """`(road_km, encoded_polyline)` for origin -> dest via the Routes API
    computeRoutes, for the route map. Mock mode (and a missing/absent route) returns the
    haversine distance and an EMPTY polyline, so the caller draws a straight segment
    between the two points instead of a road line."""
    if settings.calculator_mock:
        return _haversine_km(origin, dest), ""
    if not settings.google_static_maps_api_key:
        raise MapsError("google_static_maps_api_key is not configured")

    headers = {
        HEADER_API_KEY: settings.google_static_maps_api_key,
        HEADER_FIELD_MASK: COMPUTE_FIELD_MASK,
    }
    payload = {
        COMPUTE_KEY_ORIGIN: _location(origin),
        COMPUTE_KEY_DESTINATION: _location(dest),
        ROUTES_KEY_TRAVEL_MODE: ROUTES_TRAVEL_MODE_DRIVE,
        ROUTES_KEY_ROUTING_PREFERENCE: ROUTES_ROUTING_PREFERENCE,
    }
    owns = client is None
    http = client or httpx.AsyncClient(timeout=settings.maps_request_timeout_seconds)
    try:
        response = await http.post(
            settings.google_maps_compute_routes_url, headers=headers, json=payload
        )
        response.raise_for_status()
        body = response.json()
    except httpx.HTTPError as exc:
        logger.exception("computeRoutes request failed")
        koerper = getattr(getattr(exc, "response", None), "text", "") or ""
        detail = f" — {koerper[:500]}" if koerper else ""
        raise MapsError(f"{exc}{detail}") from exc
    finally:
        if owns:
            await http.aclose()

    routes = body.get(COMPUTE_KEY_ROUTES) or []
    if not routes:
        return _haversine_km(origin, dest), ""  # no route -> straight-line fallback
    top = routes[0]
    km = (Decimal(top.get(ROUTES_KEY_DISTANCE_METERS, 0)) / 1000).quantize(KM_QUANT)
    polyline = (top.get(COMPUTE_KEY_POLYLINE) or {}).get(COMPUTE_KEY_ENCODED, "")
    return km, polyline
