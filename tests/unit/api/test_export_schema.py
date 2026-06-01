from __future__ import annotations

import subprocess

import pytest

from scripts.export_schema import (
    BODY_MODELS,
    JSON2TS,
    PINNED_MODELS,
    UNIONS,
    _bundle_schema,
    _run_json2ts,
    render,
)


def _json2ts_runnable() -> bool:
    if not JSON2TS.exists():
        return False
    try:
        _run_json2ts(_bundle_schema([BODY_MODELS[0]], "Probe"))
    except (subprocess.CalledProcessError, OSError):
        return False
    return True


pytestmark = pytest.mark.skipif(
    not _json2ts_runnable(), reason="json2ts not available (run npm install in ui/)"
)


def test_render_contains_every_interface() -> None:
    ts = render()
    for model in BODY_MODELS + PINNED_MODELS:
        assert f"export interface {model.__name__} " in ts


def test_render_contains_unions() -> None:
    ts = render()
    for name, _members in UNIONS:
        assert f"export type {name} =" in ts


def test_render_is_stable() -> None:
    assert render() == render()
