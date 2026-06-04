"""Google Static Maps client.

Fetches a single static map PNG for a street address. Google geocodes the address string
inline (passed as both `center` and a marker), so no separate Geocoding API call is needed and
the API key can be restricted to the Maps Static API alone. The image is requested at
``size=320x320`` with ``scale=2``, which Google returns as a 640x640 PNG (scale doubles the
pixel density, not the geographic coverage). The key comes from
``settings.google_static_maps_api_key``; the call raises ``StaticMapError`` if it is unset or the
request fails.

``static_map_id`` derives a deterministic content-addressed id from the request params so the
same address/zoom/maptype always maps to one storage object.
"""

from __future__ import annotations

import hashlib
import logging

import httpx

from shared.config import settings

logger = logging.getLogger(__name__)

STATIC_MAPS_URL = "https://maps.googleapis.com/maps/api/staticmap"

# Static Maps request params. These name an external contract; both the request and the
# content-addressed id below reference these same constants.
PARAM_CENTER = "center"
PARAM_ZOOM = "zoom"
PARAM_SIZE = "size"
PARAM_SCALE = "scale"
PARAM_MARKERS = "markers"
PARAM_MAPTYPE = "maptype"
PARAM_FORMAT = "format"
PARAM_KEY = "key"

# Static Maps caps a single request at 640x640; size=320x320 with scale=2 yields a 640x640 PNG.
MAP_SIZE = "320x320"
MAP_SCALE = 2
MAP_FORMAT = "png"
MAP_CONTENT_TYPE = "image/png"
MARKER_COLOR = "red"

MAPTYPE_ROADMAP = "roadmap"

REQUEST_TIMEOUT_SECONDS = 30.0


class StaticMapError(Exception):
    """Raised when a static map cannot be fetched (missing key or a failed request)."""


def static_map_id(address: str, zoom: int, maptype: str) -> str:
    """Content-addressed id for a rendered map, stable across calls with the same params."""
    raw = f"{address}|{zoom}|{maptype}|{MAP_SIZE}|{MAP_SCALE}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def fetch_static_map_png(
    address: str,
    *,
    zoom: int,
    maptype: str = MAPTYPE_ROADMAP,
    client: httpx.AsyncClient | None = None,
) -> bytes:
    """Fetch an 800x800 PNG centered on `address` with a single red marker."""
    if not settings.google_static_maps_api_key:
        raise StaticMapError("GOOGLE_STATIC_MAPS_API_KEY is not configured")

    params = {
        PARAM_CENTER: address,
        PARAM_ZOOM: zoom,
        PARAM_SIZE: MAP_SIZE,
        PARAM_SCALE: MAP_SCALE,
        PARAM_MAPTYPE: maptype,
        PARAM_FORMAT: MAP_FORMAT,
        PARAM_MARKERS: f"color:{MARKER_COLOR}|{address}",
        PARAM_KEY: settings.google_static_maps_api_key,
    }

    owns_client = client is None
    http = client or httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS)
    try:
        response = await http.get(STATIC_MAPS_URL, params=params)
        response.raise_for_status()
        return response.content
    except httpx.HTTPError as exc:
        logger.exception("Static map request failed for address=%s", address)
        raise StaticMapError(str(exc)) from exc
    finally:
        if owns_client:
            await http.aclose()
