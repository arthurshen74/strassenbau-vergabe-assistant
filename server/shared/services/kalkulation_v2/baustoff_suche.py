"""
baustoff_suche.py — BM25 match from an LV text (Kurztext/Langtext) to a Baustoff code.

The LV text carries the normed material designation (TL SoB-StB / TL Asphalt-StB: a
Körnung like '0/32', a type code like 'AC 11 D S'), so material selection is a
text -> catalog matching problem whose answer sits in the source text in a controlled
vocabulary. This hand-rolled Okapi-BM25 index over the small BAUSTOFFE catalog grounds
that text to a REAL catalog code — it can only ever return a cataloged code, so there is
no hallucinated-code failure mode. The graph pre-fills the Gate A Baustoff picker with the
top hit; a confidence below settings.calculator_baustoff_match_threshold is left for the
Kalkulator to confirm/choose (HITL). When the catalog is replaced with real supplier data,
this matcher is unchanged.

`konfidenz` is the separation between the two best hits, top1 / (top1 + top2) — in [0.5, 1]
for any positive hit, 0.0 when nothing matches. A clear winner approaches 1.0; two equally
plausible grades approach 0.5. The auto/HITL threshold is therefore tuned in (0.5, 1].
"""

from __future__ import annotations

import math
import re
from collections import Counter

from pydantic import BaseModel, ConfigDict

from shared.services.kalkulation_v2.materialien import BAUSTOFFE
from shared.services.kalkulation_v2.model import Baustoff

_K1 = 1.5
_B = 0.75
_KOERNUNG = re.compile(r"\d+/\d+")            # keep '0/32' as one strong token
_WORT = re.compile(r"[a-zäöüß0-9]+", re.IGNORECASE)


def _tokenize(text: str) -> list[str]:
    t = text.lower()
    return _KOERNUNG.findall(t) + _WORT.findall(t)


def _doc_text(b: Baustoff) -> str:
    return " ".join(filter(None, [b.name, b.koernung, b.kategorie]))


class _BM25:
    def __init__(self, baustoffe: dict[str, Baustoff]) -> None:
        self.codes = list(baustoffe.keys())
        self.tf = {c: Counter(_tokenize(_doc_text(b))) for c, b in baustoffe.items()}
        self.len = {c: sum(tf.values()) for c, tf in self.tf.items()}
        self.avglen = (sum(self.len.values()) / len(self.codes)) if self.codes else 0.0
        n = len(self.codes)
        df: Counter[str] = Counter()
        for tf in self.tf.values():
            df.update(tf.keys())
        self.idf = {t: math.log(1 + (n - d + 0.5) / (d + 0.5)) for t, d in df.items()}

    def score(self, query: str) -> list[tuple[str, float]]:
        q = set(_tokenize(query))
        ranked: list[tuple[str, float]] = []
        for c in self.codes:
            tf, dl = self.tf[c], self.len[c]
            s = 0.0
            for t in q & tf.keys():
                f = tf[t]
                s += self.idf.get(t, 0.0) * (f * (_K1 + 1)) / (
                    f + _K1 * (1 - _B + _B * dl / self.avglen))
            ranked.append((c, s))
        ranked.sort(key=lambda x: x[1], reverse=True)
        return ranked


class BaustoffTreffer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str
    name: str
    score: float


class BaustoffMatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    treffer: list[BaustoffTreffer]      # top-n, score-descending (empty if nothing matched)
    konfidenz: float                    # top1 / (top1 + top2); 0.0 if no positive hit

    @property
    def top(self) -> BaustoffTreffer | None:
        return self.treffer[0] if self.treffer else None


_INDEX = _BM25(BAUSTOFFE)


def suche_baustoff(text: str, *, top_n: int = 5) -> BaustoffMatch:
    """BM25-match an LV text to the Baustoff catalog. Returns the top-n grounded hits and a
    separation confidence; the caller compares konfidenz against the configured threshold."""
    ranked = [(c, s) for c, s in _INDEX.score(text) if s > 0][:top_n]
    if not ranked:
        return BaustoffMatch(treffer=[], konfidenz=0.0)
    top1 = ranked[0][1]
    top2 = ranked[1][1] if len(ranked) > 1 else 0.0
    konfidenz = top1 / (top1 + top2) if (top1 + top2) > 0 else 0.0
    treffer = [BaustoffTreffer(code=c, name=BAUSTOFFE[c].name, score=round(s, 4))
               for c, s in ranked]
    return BaustoffMatch(treffer=treffer, konfidenz=round(konfidenz, 4))
