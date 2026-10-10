from __future__ import annotations

from pathlib import Path

import pytest

from scripts.seed.rag_queries import (
    RagQueryFileError,
    load_rag_query_versions,
    parse_rag_query_file,
)
from shared.db.tables.projects import projects
from shared.models.enums import ProjectInfoQuery
from shared.models.rag_query import PROJECT_INFO_TARGET_COLUMN

SEED_LANGUAGE = "de"


def test_shipped_files_cover_every_key_in_german() -> None:
    versions = load_rag_query_versions()
    german = {v.query_key for v in versions if v.language == SEED_LANGUAGE}
    assert german == set(ProjectInfoQuery)


def test_shipped_files_have_non_empty_texts() -> None:
    for v in load_rag_query_versions():
        assert v.name and v.description and v.query_text and v.answer_instruction


def test_every_key_targets_a_projects_column() -> None:
    assert set(PROJECT_INFO_TARGET_COLUMN) == set(ProjectInfoQuery)
    for column in PROJECT_INFO_TARGET_COLUMN.values():
        assert column in projects.c


def test_parse_takes_key_and_language_from_filename(tmp_path: Path) -> None:
    f = tmp_path / "project-name.en.yaml"
    f.write_text(
        "name: Name\ndescription: d\nquery_text: q\nanswer_instruction: a\n",
        encoding="utf-8",
    )
    parsed = parse_rag_query_file(f)
    assert parsed.query_key is ProjectInfoQuery.PROJECT_NAME
    assert parsed.language == "en"


def test_parse_rejects_unknown_key(tmp_path: Path) -> None:
    f = tmp_path / "project-unknown.de.yaml"
    f.write_text("name: x\n", encoding="utf-8")
    with pytest.raises(RagQueryFileError, match="not a ProjectInfoQuery"):
        parse_rag_query_file(f)


def test_parse_rejects_missing_field(tmp_path: Path) -> None:
    f = tmp_path / "project-name.de.yaml"
    f.write_text("name: x\ndescription: d\nquery_text: q\n", encoding="utf-8")
    with pytest.raises(RagQueryFileError, match="invalid fields"):
        parse_rag_query_file(f)
