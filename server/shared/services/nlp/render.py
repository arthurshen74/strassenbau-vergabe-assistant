"""Displacy renders for single sentences.

dep -> SVG, cached in nlp_render_cache keyed by sha256(model, version, style, text);
a model upgrade is a clean cache miss (key changes), never a stale hit.
ent -> HTML, regenerated per request via displacy manual mode from the Doc's
entities — model-agnostic, so EntityRuler output plugs in later unchanged.
"""

from __future__ import annotations

import hashlib

from sqlalchemy.ext.asyncio import AsyncEngine

from shared.db.unit_of_work import unit_of_work
from shared.models.enums import RenderStyle
from shared.services.nlp.analysis import get_nlp, spacy_model_version


def render_cache_key(style: RenderStyle, text: str) -> str:
    return hashlib.sha256(f"{spacy_model_version()}|{style}|{text}".encode()).hexdigest()


def render_dep_svg(text: str) -> str:
    from spacy import displacy

    nlp = get_nlp()
    doc = nlp(text)  # type: ignore[operator]
    return displacy.render(doc, style=RenderStyle.DEP.value, jupyter=False)


def render_ent_html(text: str) -> str:
    from spacy import displacy

    nlp = get_nlp()
    doc = nlp(text)  # type: ignore[operator]
    return displacy.render(doc, style=RenderStyle.ENT.value, jupyter=False, page=False)


class RenderService:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def render(self, style: RenderStyle, text: str) -> str:
        if style is RenderStyle.ENT:
            return render_ent_html(text)

        cache_key = render_cache_key(RenderStyle.DEP, text)
        async with unit_of_work(self._engine) as uow:
            cached = await uow.nlp_render_cache.get(cache_key)
        if cached is not None:
            return cached

        markup = render_dep_svg(text)
        async with unit_of_work(self._engine) as uow:
            await uow.nlp_render_cache.put(cache_key, RenderStyle.DEP.value, markup)
        return markup
