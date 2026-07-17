"""Dispatcher tool registry: declarative tool definitions executed via direct service
calls."""

from __future__ import annotations

from shared.tools._base import ToolContext, ToolDefinition
from shared.tools.registry import TOOL_CATALOGS, catalog_for, tool_by_name

__all__ = [
    "TOOL_CATALOGS",
    "ToolContext",
    "ToolDefinition",
    "catalog_for",
    "tool_by_name",
]
