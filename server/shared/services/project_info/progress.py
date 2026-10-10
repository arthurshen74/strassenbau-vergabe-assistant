"""Phases of a Projektinfo job, stamped on its activity lines."""

from __future__ import annotations

from enum import StrEnum


class ProjectInfoPhase(StrEnum):
    CLAIM = "claim"
    RETRIEVE = "retrieve"
    SYNTHESIZE = "synthesize"
    WRITE = "write"
