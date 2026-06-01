from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# Action is a Literal, not a StrEnum: this schema is sent to the provider verbatim with
# strict=True, and a StrEnum field serializes to $ref/$defs, which strict structured output
# forbids. A Literal inlines as a plain string enum.
ProjectChatAction = Literal[
    "lv_item_lookup",
    "list_lv_items_by_parent_oz",
    "rag_retrieval",
    "refuse",
]


class ProjectChatRoute(BaseModel):
    """Structured routing decision for one project-chat user message: the chosen action and
    its argument. Exactly one argument is populated per action (none for `refuse`); the others
    are null. The action/argument pairing can't be expressed without a union, so the service
    validates that the right argument is present after parsing.

    Every field is required: strict structured output lists all properties as required, so
    inapplicable arguments come back null rather than omitted.
    """

    model_config = ConfigDict(extra="forbid")

    action: ProjectChatAction = Field(
        description="The single action that best serves the latest user message."
    )
    oz: str | None = Field(
        description="The Ordnungszahl to look up, verbatim as written (e.g. '01.02.0030'). "
        "Set only for action 'lv_item_lookup'; otherwise null."
    )
    parent_oz: str | None = Field(
        description="The section Ordnungszahl whose child positions to list (e.g. '01.02'). "
        "Set only for action 'list_lv_items_by_parent_oz'; otherwise null."
    )
    search_query: str | None = Field(
        description="A standalone, context-resolved reformulation of the question for retrieval, "
        "in the language of the question. Set only for action 'rag_retrieval'; otherwise null."
    )
