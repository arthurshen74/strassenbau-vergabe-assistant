from __future__ import annotations

from pathlib import Path

import pytest

from scripts.seed.prompts import (
    PromptFileError,
    load_prompt_versions,
    parse_prompt_file,
)
from shared.models.enums import PromptType


def _write(tmp_path: Path, name: str, content: str) -> Path:
    f = tmp_path / name
    f.write_text(content)
    return f


def test_shipped_prompt_files_cover_every_prompt_type() -> None:
    versions = load_prompt_versions()
    # ekt_calculator's prompts are hardcoded in shared/services/calculator/llm_calls.py, not the
    # prompt registry, so it ships no .prompt file.
    expected = set(PromptType) - {PromptType.EKT_CALCULATOR}
    assert {v.prompt_type for v in versions} == expected


def test_parse_valid_file(tmp_path: Path) -> None:
    f = _write(
        tmp_path,
        "dispatcher.prompt",
        "---\nmodel_name: some/model\ntemperature: 0.2\ntop_p: 0.9\n---\nDo the thing.\n",
    )
    pv = parse_prompt_file(f)
    assert pv.prompt_type is PromptType.DISPATCHER
    assert pv.model_name == "some/model"
    assert pv.temperature == 0.2
    assert pv.top_p == 0.9
    assert pv.system_prompt == "Do the thing."


def test_optional_fields_default(tmp_path: Path) -> None:
    f = _write(tmp_path, "dispatcher.prompt", "---\nmodel_name: m\n---\nBody.\n")
    pv = parse_prompt_file(f)
    assert pv.temperature == 0.0
    assert pv.top_p is None


def test_null_temperature_parses_to_none(tmp_path: Path) -> None:
    f = _write(tmp_path, "dispatcher.prompt", "---\nmodel_name: m\ntemperature: null\n---\nBody.\n")
    assert parse_prompt_file(f).temperature is None


def test_body_preserved_verbatim_with_outer_whitespace_stripped(tmp_path: Path) -> None:
    body = "Rewrite into {{n}} phrasings.\nReturn exactly {{n}} variants."
    f = _write(
        tmp_path,
        "multi_question_generator.prompt",
        f"---\nmodel_name: m\n---\n\n{body}\n\n",
    )
    assert parse_prompt_file(f).system_prompt == body


@pytest.mark.parametrize(
    "name, content",
    [
        ("dispatcher.prompt", "model_name: m\nbody"),
        ("dispatcher.prompt", "---\nmodel_name: m\n"),
        ("dispatcher.prompt", "---\nmodel_name: m\nfoo: bar\n---\nbody"),
        ("dispatcher.prompt", "---\ntemperature: 0.0\n---\nbody"),
        ("dispatcher.prompt", "---\nmodel_name: m\n---\n\n"),
        ("dispatcher.prompt", "---\nmodel_name: m\nsystem_prompt: x\n---\nbody"),
        ("_notatype.prompt", "---\nmodel_name: m\n---\nbody"),
    ],
    ids=[
        "no-opening-fence",
        "no-closing-fence",
        "unknown-field",
        "missing-model-name",
        "empty-body",
        "derived-key-in-frontmatter",
        "stem-not-a-prompt-type",
    ],
)
def test_malformed_files_raise(tmp_path: Path, name: str, content: str) -> None:
    f = _write(tmp_path, name, content)
    with pytest.raises(PromptFileError):
        parse_prompt_file(f)


def test_empty_directory_raises(tmp_path: Path) -> None:
    with pytest.raises(PromptFileError):
        load_prompt_versions(tmp_path)
