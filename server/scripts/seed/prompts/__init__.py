"""Load PromptVersion seed definitions from `.prompt` files.

Each `.prompt` file defines the current prompt for one PromptType: YAML frontmatter
carries the tunables (model_name, temperature, top_p) and the document body is the
system prompt verbatim, including any `{{placeholder}}` templates. The prompt_type is
the filename stem; `version` is never authored here -- the repository assigns the next
integer on insert, so re-running the seed appends a new version.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from shared.models.enums import PromptType
from shared.models.prompt_version import NewPromptVersion

PROMPT_FILE_SUFFIX = ".prompt"
FRONTMATTER_FENCE = "---"

# Fields a `.prompt` file must not set: the type is the filename and the system
# prompt is the body, so authoring either in frontmatter is a mistake.
_DERIVED_KEYS = ("prompt_type", "system_prompt")


class PromptFileError(Exception):
    """A `.prompt` seed file is malformed or fails validation."""


def load_prompt_versions(directory: Path | None = None) -> list[NewPromptVersion]:
    """Parse every `.prompt` file in `directory` (default: this package), sorted by name."""
    directory = directory or Path(__file__).parent
    paths = sorted(directory.glob(f"*{PROMPT_FILE_SUFFIX}"))
    if not paths:
        raise PromptFileError(f"no {PROMPT_FILE_SUFFIX} files in {directory}")
    return [parse_prompt_file(p) for p in paths]


def parse_prompt_file(path: Path) -> NewPromptVersion:
    """Parse one `.prompt` file into a NewPromptVersion (version unassigned)."""
    try:
        prompt_type = PromptType(path.stem)
    except ValueError as exc:
        raise PromptFileError(
            f"{path.name}: filename stem '{path.stem}' is not a PromptType"
        ) from exc

    meta, body = _split_frontmatter(path)
    if not body:
        raise PromptFileError(f"{path.name}: empty system prompt body")
    for key in _DERIVED_KEYS:
        if key in meta:
            raise PromptFileError(
                f"{path.name}: '{key}' is derived from the file, not set in frontmatter"
            )
    try:
        return NewPromptVersion(prompt_type=prompt_type, system_prompt=body, **meta)
    except ValidationError as exc:
        raise PromptFileError(f"{path.name}: invalid frontmatter\n{exc}") from exc


def _split_frontmatter(path: Path) -> tuple[dict[str, object], str]:
    """Split a frontmatter document into its parsed YAML mapping and stripped body."""
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != FRONTMATTER_FENCE:
        raise PromptFileError(
            f"{path.name}: must open with a '{FRONTMATTER_FENCE}' frontmatter fence"
        )
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == FRONTMATTER_FENCE)
    except StopIteration:
        raise PromptFileError(
            f"{path.name}: missing closing '{FRONTMATTER_FENCE}' frontmatter fence"
        ) from None

    meta = yaml.safe_load("\n".join(lines[1:end])) or {}
    if not isinstance(meta, dict):
        raise PromptFileError(f"{path.name}: frontmatter is not a mapping")
    body = "\n".join(lines[end + 1 :]).strip()
    return meta, body
