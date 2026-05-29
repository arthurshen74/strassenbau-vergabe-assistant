from __future__ import annotations

import pytest

from scripts.export_schema import JSON2TS, BODY_MODELS, PINNED_MODELS, render

pytestmark = pytest.mark.skipif(
    not JSON2TS.exists(), reason="json2ts toolchain not installed (run npm install in ui/)"
)


def test_render_contains_ingest_event_union() -> None:
    output = render()
    assert "export type IngestEvent =" in output
    for member in PINNED_MODELS:
        assert f"  | {member.__name__}" in output


def test_render_contains_all_dto_interfaces() -> None:
    output = render()
    for model in BODY_MODELS + PINNED_MODELS:
        assert f"export interface {model.__name__} {{" in output


def test_render_is_stable_across_calls() -> None:
    assert render() == render()


def test_render_has_no_interview_prep_symbols() -> None:
    output = render()
    for stale in ("IPAPrompt", "Interviewer", "PositionDTO", "ConversationDTO"):
        assert stale not in output
