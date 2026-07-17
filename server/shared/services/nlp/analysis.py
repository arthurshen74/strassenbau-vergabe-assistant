"""spaCy analysis over reflowed blocks: sentences and POS statistics.

The pipeline (de_core_news_lg) is a lazy module singleton — loaded on first use,
never at API boot (design D5). Each included block runs as its own Doc via
nlp.pipe: sentences never legitimately cross block boundaries, and per-block Docs
keep sentence hashes stable for the render cache.

A sentence hash is sha256(model name, model version, sentence text) — the same key
prefix the render cache uses, so the render endpoint can re-derive everything it
needs from the hash owner (the analyze response holds hash -> text).
"""

from __future__ import annotations

import hashlib
import threading
from collections import defaultdict

from shared.models.enums import BlockType
from shared.models.nlp import (
    PosStats,
    PosTagStats,
    ReflowedBlock,
    SentenceInfo,
    TokenInfo,
)

SPACY_MODEL = "de_core_news_lg"

# Tags never counted in POS statistics: whitespace and non-linguistic artifacts.
_EXCLUDED_POS = frozenset({"SPACE"})

_nlp_lock = threading.Lock()
_nlp: object | None = None


def get_nlp() -> object:
    """Lazy spaCy pipeline singleton; loads the model on first call."""
    global _nlp
    with _nlp_lock:
        if _nlp is None:
            import spacy

            _nlp = spacy.load(SPACY_MODEL)
        return _nlp


def spacy_model_version() -> str:
    nlp = get_nlp()
    return f"{SPACY_MODEL}-{nlp.meta['version']}"  # type: ignore[attr-defined]


def sentence_hash(text: str) -> str:
    return hashlib.sha256(f"{spacy_model_version()}|{text}".encode()).hexdigest()


def analyze_blocks(
    blocks: list[ReflowedBlock], include_blocks: list[BlockType]
) -> tuple[list[SentenceInfo], PosStats]:
    """Sentences and POS distribution over the blocks whose type is included."""
    nlp = get_nlp()
    included = [b for b in blocks if b.block_type in include_blocks]

    sentences: list[SentenceInfo] = []
    ud_tokens: dict[str, list[TokenInfo]] = defaultdict(list)
    stts_tokens: dict[str, list[TokenInfo]] = defaultdict(list)
    token_count = 0

    docs = nlp.pipe([b.text for b in included])  # type: ignore[attr-defined]
    for block, doc in zip(included, docs):
        for sent in doc.sents:
            text = sent.text.strip()
            if not text:
                continue
            s_hash = sentence_hash(text)
            sentences.append(
                SentenceInfo(sentence_hash=s_hash, block_id=block.block_id, text=text)
            )
            for token in sent:
                if token.pos_ in _EXCLUDED_POS:
                    continue
                token_count += 1
                info = TokenInfo(text=token.text, lemma=token.lemma_, sentence_hash=s_hash)
                ud_tokens[token.pos_].append(info)
                stts_tokens[token.tag_].append(info)

    return sentences, PosStats(
        token_count=token_count,
        ud=_tag_stats(ud_tokens, token_count),
        stts=_tag_stats(stts_tokens, token_count),
    )


def _tag_stats(tokens_by_tag: dict[str, list[TokenInfo]], total: int) -> list[PosTagStats]:
    stats = [
        PosTagStats(
            tag=tag,
            count=len(tokens),
            percentage=round(100.0 * len(tokens) / total, 2) if total else 0.0,
            tokens=tokens,
        )
        for tag, tokens in tokens_by_tag.items()
    ]
    stats.sort(key=lambda s: s.count, reverse=True)
    return stats
