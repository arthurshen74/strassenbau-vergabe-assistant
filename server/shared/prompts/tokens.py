from __future__ import annotations

import re

_TOKEN_RE = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")


class UnresolvedTokenError(ValueError):
    pass


def substitute(template: str, tokens: dict[str, str] | None) -> str:
    values = tokens or {}
    missing: list[str] = []

    def _replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in values:
            missing.append(name)
            return match.group(0)
        return values[name]

    result = _TOKEN_RE.sub(_replace, template)
    if missing:
        unique = sorted(set(missing))
        raise UnresolvedTokenError(
            f"unresolved tokens in prompt: {', '.join(unique)}"
        )
    return result
