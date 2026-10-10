"""Load RagQueryVersion seed definitions from `.yaml` files.

Each file is named `<query_key>.<language>.yaml` and carries `name`, `description`,
`query_text` and `answer_instruction`. The query_key and language come from the
filename; `version` is never authored here -- the repository assigns the next integer
on insert, so re-running the seed appends a new version.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from shared.models.enums import ProjectInfoQuery
from shared.models.rag_query import NewRagQueryVersion

RAG_QUERY_FILE_SUFFIX = ".yaml"


class RagQueryFileError(Exception):
    """A rag query seed file is malformed or fails validation."""


def load_rag_query_versions(directory: Path | None = None) -> list[NewRagQueryVersion]:
    """Parse every `.yaml` file in `directory` (default: this package), sorted by
    name."""
    directory = directory or Path(__file__).parent
    paths = sorted(directory.glob(f"*{RAG_QUERY_FILE_SUFFIX}"))
    if not paths:
        raise RagQueryFileError(f"no {RAG_QUERY_FILE_SUFFIX} files in {directory}")
    return [parse_rag_query_file(p) for p in paths]


def parse_rag_query_file(path: Path) -> NewRagQueryVersion:
    """Parse one `<query_key>.<language>.yaml` file (version unassigned)."""
    key, _, language = path.stem.rpartition(".")
    try:
        query_key = ProjectInfoQuery(key)
    except ValueError as exc:
        raise RagQueryFileError(
            f"{path.name}: '{key}' is not a ProjectInfoQuery"
        ) from exc

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RagQueryFileError(f"{path.name}: not a mapping")
    try:
        return NewRagQueryVersion(query_key=query_key, language=language, **data)
    except ValidationError as exc:
        raise RagQueryFileError(f"{path.name}: invalid fields\n{exc}") from exc
