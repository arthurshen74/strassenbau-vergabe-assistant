"""API schema for the retrieval knobs a project-chat turn carries.

The frontend sends this with each `project_chat` turn so the user can switch the RAG modality and
toggle the optional stages per message. It is the request-side counterpart of the service-layer
`RetrievalConfig`; the pool/result size knobs are not user-facing and stay on the `settings.*`
defaults. The service maps this DTO to a `RetrievalConfig` (the model layer never imports the
service layer)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from shared.models.enums import RetrievalModality


class TurnRetrievalConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    modality: RetrievalModality = RetrievalModality.SIMPLE
    multi_query: bool = False
    use_bm25: bool = False
    use_cross_encoder: bool = False
