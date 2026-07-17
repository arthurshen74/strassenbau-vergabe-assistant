"""Boundary validation for user chat input.

A heuristic first line of defence in front of the prompt-level guardrails: it rejects
input that
is empty, oversize, carries control characters, or matches common prompt-injection /
jailbreak
phrasings before the text ever reaches the dispatcher LLM. It is not a substitute for
the
system-prompt guardrails -- both layers run. Violations raise InputRejectedError, which
the chat
route maps to HTTP 400.
"""

from __future__ import annotations

import re

# Upper bound on a single chat message; longer input is refused outright (cheap DoS
# guard).
MAX_INPUT_CHARS = 8000

# Rule identifiers surfaced on InputRejectedError (and, in turn, the 400 response).
RULE_EMPTY = "empty"
RULE_TOO_LONG = "too_long"
RULE_CONTROL_CHARS = "control_chars"
RULE_PROMPT_INJECTION = "prompt_injection"

# Control characters that never appear in legitimate chat text; tab, newline and
# carriage return
# are deliberately allowed.
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

# Special role-delimiter tokens and instruction-override / jailbreak phrasings. These
# are
# heuristics, and a match is refused, so each pattern is kept specific to an attack
# shape rather
# than to ordinary prose.
_INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    # ChatML-style role delimiters, e.g. <|im_start|>, <|endoftext|>.
    re.compile(r"<\|.*?\|>"),
    # A line that spoofs a system/assistant/developer turn.
    re.compile(r"^\s*(?:system|assistant|developer)\s*:", re.IGNORECASE | re.MULTILINE),
    re.compile(
        r"ignore\s+(?:all\s+|the\s+|any\s+)?(?:previous|prior|above|preceding|earlier)\s+"
        r"(?:instructions?|prompts?|messages?|rules?|context)",
        re.IGNORECASE,
    ),
    re.compile(
        r"disregard\s+(?:all\s+|the\s+|any\s+)?(?:previous|prior|above|preceding|earlier)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"forget\s+(?:everything|all|your|the)\b[^.]*\b(?:instructions?|rules?|prompt)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:reveal|show|print|repeat|expose|leak|disclose)\s+(?:me\s+)?(?:your\s+|the\s+)?"
        r"(?:system\s+|initial\s+|original\s+)?(?:prompt|instructions?|rules?)",
        re.IGNORECASE,
    ),
    re.compile(r"\byou\s+are\s+now\b", re.IGNORECASE),
    re.compile(r"\b(?:developer|debug|god|admin|jailbreak)\s+mode\b", re.IGNORECASE),
    re.compile(r"\bdo\s+anything\s+now\b", re.IGNORECASE),
    re.compile(
        r"\bact\s+as\s+(?:an?\s+)?(?:unfiltered|uncensored|jailbroken|unrestricted)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bbypass\s+(?:your\s+|the\s+|all\s+)?(?:restrictions?|filters?|guidelines?|safety|rules?)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bwithout\s+(?:any\s+)?(?:restrictions?|filters?|censorship|limitations?|rules?)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bnew\s+(?:system\s+)?(?:instructions?|prompt)\s*:", re.IGNORECASE),
)


class InputRejectedError(Exception):
    """User chat input failed a boundary check; `rule` names the rule that tripped."""

    def __init__(self, rule: str, message: str) -> None:
        super().__init__(message)
        self.rule = rule


def guard_user_input(text: str) -> None:
    """Validate raw user chat input, raising InputRejectedError on the first
    violation."""
    if not text.strip():
        raise InputRejectedError(RULE_EMPTY, "message must not be empty")
    if len(text) > MAX_INPUT_CHARS:
        raise InputRejectedError(
            RULE_TOO_LONG, f"message exceeds {MAX_INPUT_CHARS} characters"
        )
    if _CONTROL_CHARS.search(text):
        raise InputRejectedError(
            RULE_CONTROL_CHARS, "message contains control characters"
        )
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(text):
            raise InputRejectedError(
                RULE_PROMPT_INJECTION, "message matched a disallowed pattern"
            )
