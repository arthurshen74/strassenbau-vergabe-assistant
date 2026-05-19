from __future__ import annotations

import pytest

from shared.prompts.tokens import UnresolvedTokenError, substitute


def test_substitutes_named_tokens() -> None:
    out = substitute("Hello {{name}}, welcome to {{place}}.", {"name": "A", "place": "B"})
    assert out == "Hello A, welcome to B."


def test_no_tokens_passthrough() -> None:
    assert substitute("No markers here", None) == "No markers here"
    assert substitute("No markers here", {}) == "No markers here"


def test_whitespace_inside_markers_tolerated() -> None:
    assert substitute("Hi {{  name  }}", {"name": "X"}) == "Hi X"


def test_repeated_token_replaced_each_time() -> None:
    assert substitute("{{x}}-{{x}}-{{x}}", {"x": "A"}) == "A-A-A"


def test_extra_tokens_ignored() -> None:
    assert substitute("Hi {{name}}", {"name": "A", "unused": "B"}) == "Hi A"


def test_raises_on_unresolved() -> None:
    with pytest.raises(UnresolvedTokenError) as exc:
        substitute("Hi {{name}} {{place}}", {"name": "A"})
    assert "place" in str(exc.value)


def test_raises_lists_all_unresolved_sorted() -> None:
    with pytest.raises(UnresolvedTokenError) as exc:
        substitute("{{b}} {{a}} {{c}}", {})
    msg = str(exc.value)
    assert "a, b, c" in msg
