from __future__ import annotations

from uuid import UUID

import httpx
import pytest

from shared.clients.maps.client import (
    MAP_SCALE,
    MAP_SIZE,
    MAPTYPE_ROADMAP,
    PARAM_CENTER,
    PARAM_KEY,
    PARAM_MARKERS,
    PARAM_SCALE,
    PARAM_SIZE,
    PARAM_ZOOM,
    STATIC_MAPS_URL,
    StaticMapError,
    fetch_static_map_png,
    static_map_id,
)
from shared.clients.storage.client import MAP_KEY_PREFIX, map_object_key
from shared.config import settings

ADDRESS = "Jasperallee 86, 38102 Braunschweig, Deutschland"


def _client_with_handler(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_fetch_sends_expected_request_and_returns_bytes(monkeypatch) -> None:
    monkeypatch.setattr(settings, "google_static_maps_api_key", "test-key")
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url).split("?")[0]
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, content=b"PNGBYTES")

    png = await fetch_static_map_png(
        ADDRESS, zoom=12, client=_client_with_handler(handler)
    )

    assert png == b"PNGBYTES"
    assert captured["url"] == STATIC_MAPS_URL
    params = captured["params"]
    assert params[PARAM_CENTER] == ADDRESS
    assert params[PARAM_ZOOM] == "12"
    # size=320x320 with scale=2 is what yields a 640x640 image.
    assert params[PARAM_SIZE] == MAP_SIZE
    assert params[PARAM_SCALE] == str(MAP_SCALE)
    assert params[PARAM_MARKERS] == f"color:red|{ADDRESS}"
    assert params[PARAM_KEY] == "test-key"


async def test_fetch_raises_when_key_missing(monkeypatch) -> None:
    monkeypatch.setattr(settings, "google_static_maps_api_key", None)

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("no request expected without a key")

    with pytest.raises(StaticMapError):
        await fetch_static_map_png(ADDRESS, zoom=12, client=_client_with_handler(handler))


async def test_fetch_wraps_http_error(monkeypatch) -> None:
    monkeypatch.setattr(settings, "google_static_maps_api_key", "test-key")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text="forbidden")

    with pytest.raises(StaticMapError):
        await fetch_static_map_png(ADDRESS, zoom=12, client=_client_with_handler(handler))


def test_static_map_id_is_deterministic_and_param_sensitive() -> None:
    base = static_map_id(ADDRESS, 12, MAPTYPE_ROADMAP)
    assert base == static_map_id(ADDRESS, 12, MAPTYPE_ROADMAP)
    assert base != static_map_id(ADDRESS, 13, MAPTYPE_ROADMAP)
    assert base != static_map_id(ADDRESS, 12, "satellite")


def test_map_object_key_is_project_scoped() -> None:
    project = UUID(int=1)
    key = map_object_key(project, "abc123")
    assert key == f"{MAP_KEY_PREFIX}/{project}/abc123"
