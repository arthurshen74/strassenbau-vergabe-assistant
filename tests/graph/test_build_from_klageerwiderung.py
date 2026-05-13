"""Build Document + Paragraph + Assertion objects from the
out/data/klageerwiderung.2026.04.09.pdf.json extraction, scoped to pages 1-4.

This exercises the application-layer Pydantic models in graph/models.py
against real ingest output, and is the first concrete invocation of the
assertion-extraction logic that will become pipeline step 5.

Per-paragraph extractions are cached under .cache/assertions/ keyed by the
SHA-256 prefix of the German text, so reruns do not re-bill the API.

Run:
    python -m tests.graph.test_build_from_klageerwiderung
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path

import anthropic
from dotenv import load_dotenv

from graph.models import Assertion, Document, Paragraph

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_FILE = PROJECT_ROOT / "out/data/klageerwiderung.2026.04.09.pdf.json"
# Bumped when the extraction prompt/schema changes so stale cache entries
# (which encoded a different extraction contract) are not reused.
CACHE_DIR = PROJECT_ROOT / ".cache/assertions_v2"
OUT_FILE = PROJECT_ROOT / "out/graph/klageerwiderung_pages_1_4.json"

EXTRACT_MODEL = "claude-sonnet-4-6"
EXTRACT_MAX_TOKENS = 2048
PAGE_RANGE = range(1, 5)

CLASSIFICATION_VALUES = (
    "factual", "legal", "rhetorical", "procedural", "evidentiary",
)

ASSERTION_TOOL = {
    "name": "submit_assertions",
    "description": (
        "Extract and classify atomic claims from a single paragraph of a "
        "German Klageerwiderung. Return an empty list if the paragraph "
        "contains no analyzable atomic claims (e.g., bare headers, pure "
        "cross-references)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "assertions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "assertion_text": {
                            "type": "string",
                            "description": (
                                "The atomic claim, in German, lightly "
                                "rephrased into canonical "
                                "subject-verb-object form."
                            ),
                        },
                        "assertion_text_en": {
                            "type": "string",
                            "description": (
                                "Faithful English translation of "
                                "assertion_text."
                            ),
                        },
                        "classification": {
                            "type": "string",
                            "enum": list(CLASSIFICATION_VALUES),
                            "description": (
                                "What kind of claim this is. "
                                "'factual' = a Tatsachenbehauptung (a "
                                "verifiable fact); 'legal' = a legal "
                                "characterization or conclusion "
                                "(e.g., 'this constitutes Vorsatz'); "
                                "'evidentiary' = a claim about what an "
                                "exhibit or piece of evidence shows; "
                                "'procedural' = a procedural reference "
                                "or position (e.g., 'die Klage ist "
                                "unbegründet'); 'rhetorical' = "
                                "argumentative framing without an "
                                "independent verifiable claim."
                            ),
                        },
                        "is_negative": {
                            "type": "boolean",
                            "description": (
                                "True iff the claim affirmatively states "
                                "that something did NOT happen."
                            ),
                        },
                    },
                    "required": [
                        "assertion_text",
                        "assertion_text_en",
                        "classification",
                        "is_negative",
                    ],
                },
            }
        },
        "required": ["assertions"],
    },
}

EXTRACT_SYSTEM = (
    "You are reading paragraphs from a German Klageerwiderung (defendant's "
    "answer) in a Kündigungsschutzklage. For each paragraph, extract every "
    "atomic claim the paragraph makes — regardless of whether it is a "
    "factual claim, a legal characterization, an evidentiary claim, or a "
    "procedural position — and classify each.\n\n"
    "Rules:\n"
    "- Return an empty list only if the paragraph contains no analyzable "
    "atomic claims (bare headers, pure cross-references such as 'siehe "
    "Anlage A 3', or stand-alone connective phrases).\n"
    "- Split a sentence containing multiple distinct claims into separate "
    "atomic assertions (one subject + verb + object/predicate each).\n"
    "- Use the original German for assertion_text; translate to English for "
    "assertion_text_en.\n"
    "- classification is one of: factual, legal, rhetorical, procedural, "
    "evidentiary. Choose the single best fit per assertion.\n"
    "- Set is_negative=true only when the assertion affirmatively states "
    "that something did NOT happen (e.g., 'der Kläger erhielt keine "
    "Abmahnung').\n"
    "- Do not invent or infer claims beyond what the paragraph states."
)


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def extract_assertions(
    client: anthropic.Anthropic,
    *,
    text_de: str,
    text_en: str,
    where: str,
) -> list[dict]:
    """Return a list of {assertion_text, assertion_text_en, is_negative}.
    Cached by SHA-256 prefix of the German text."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE_DIR / f"{_text_hash(text_de)}.json"
    if cache_path.is_file():
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        if cached.get("text_de") == text_de:
            return cached["assertions"]

    user_msg = f"DE: {text_de}\n\nEN: {text_en}"
    response = client.messages.create(
        model=EXTRACT_MODEL,
        max_tokens=EXTRACT_MAX_TOKENS,
        temperature=0.0,
        system=EXTRACT_SYSTEM,
        tools=[ASSERTION_TOOL], # type: ignore
        tool_choice={"type": "tool", "name": ASSERTION_TOOL["name"]},
        messages=[{"role": "user", "content": user_msg}],
    )
    tool_input = None
    for block in response.content:
        if (
            getattr(block, "type", None) == "tool_use"
            and block.name == ASSERTION_TOOL["name"] # type: ignore
        ):
            tool_input = block.input # type: ignore
            break
    if tool_input is None:
        raise RuntimeError(f"{where}: no submit_assertions tool_use in response")

    assertions = tool_input.get("assertions", [])
    if not isinstance(assertions, list):
        raise RuntimeError(
            f"{where}: tool returned non-list assertions: {type(assertions).__name__}"
        )

    cache_path.write_text(
        json.dumps(
            {"text_de": text_de, "assertions": assertions},
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return assertions


def build_document() -> Document:
    return Document(
        id="klageerwiderung_2026_04_09",
        document_type="Klageerwiderung",
        filing_date=date(2026, 4, 9),
        filing_party="defendant",
        aktenzeichen="797/25",
        total_pages=18,
        source_file="reference/klageerwiderung_2026_04_09.pdf",
        ingested_at=datetime.now(),
    )


def build_paragraphs(
    document: Document, records: list[dict]
) -> list[Paragraph]:
    paragraphs: list[Paragraph] = []
    for position, rec in enumerate(records, start=1):
        page = int(rec["page"])
        para = int(rec["paragraph"])
        paragraphs.append(
            Paragraph(
                id=Paragraph.build_id(document.id, page, para),
                page=page,
                paragraph=para,
                text_de=rec["text"],
                text_en=rec.get("translation"),
                position=position,
            )
        )
    return paragraphs


def build_assertions_for_paragraphs(
    client: anthropic.Anthropic,
    paragraphs: list[Paragraph],
    records_by_id: dict[str, dict],
) -> dict[str, list[Assertion]]:
    by_paragraph: dict[str, list[Assertion]] = {}
    extracted_at = datetime.now()
    for para in paragraphs:
        rec = records_by_id[para.id]
        items = extract_assertions(
            client,
            text_de=rec["text"],
            text_en=rec.get("translation", ""),
            where=para.id,
        )
        para_assertions: list[Assertion] = []
        for n, item in enumerate(items, start=1):
            para_assertions.append(
                Assertion(
                    id=Assertion.build_id(para.id, n),
                    assertion_text=item["assertion_text"],
                    assertion_text_en=item["assertion_text_en"],
                    classification=item["classification"],
                    is_negative=item["is_negative"],
                    extracted_at=extracted_at,
                )
            )
        by_paragraph[para.id] = para_assertions
    return by_paragraph


def test_build_pages_1_4() -> None:
    load_dotenv(PROJECT_ROOT / ".env")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError(
            "ANTHROPIC_API_KEY not set; prime .cache/assertions/ to skip the API"
        )
    if not DATA_FILE.is_file():
        raise RuntimeError(f"input data file not found: {DATA_FILE}")

    raw = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    pages = set(PAGE_RANGE)
    records = [r for r in raw if r.get("page") in pages]
    records.sort(key=lambda r: (r["page"], r["paragraph"]))
    assert records, "no records found for pages 1-4"

    document = build_document()
    paragraphs = build_paragraphs(document, records)

    assert len(paragraphs) == len(records)
    ids = {p.id for p in paragraphs}
    assert len(ids) == len(paragraphs), "duplicate Paragraph.id"
    for p in paragraphs:
        assert p.id.startswith(document.id + "_p")

    client = anthropic.Anthropic()
    records_by_id = {
        Paragraph.build_id(document.id, r["page"], r["paragraph"]): r
        for r in records
    }
    by_paragraph = build_assertions_for_paragraphs(client, paragraphs, records_by_id)

    all_assertions = [a for v in by_paragraph.values() for a in v]
    assertion_ids = {a.id for a in all_assertions}
    assert len(assertion_ids) == len(all_assertions), "duplicate Assertion.id"
    for para in paragraphs:
        for a in by_paragraph[para.id]:
            assert a.id.startswith(para.id + "_assertion_")

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(
        json.dumps(
            {
                "document": document.model_dump(mode="json"),
                "paragraphs": [
                    {
                        **p.model_dump(mode="json"),
                        "assertions": [
                            a.model_dump(mode="json") for a in by_paragraph[p.id]
                        ],
                    }
                    for p in paragraphs
                ],
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print(f"Document: {document.id}")
    print(f"Paragraphs (pages 1-4): {len(paragraphs)}")
    print(f"Assertions extracted:   {len(all_assertions)}")
    empties = sum(1 for v in by_paragraph.values() if not v)
    print(f"Paragraphs with 0 assertions: {empties}")
    counts = [len(v) for v in by_paragraph.values() if v]
    if counts:
        print(
            f"Assertions per non-empty paragraph: "
            f"min={min(counts)} max={max(counts)} "
            f"mean={sum(counts) / len(counts):.2f}"
        )
    from collections import Counter
    by_class = Counter(a.classification for a in all_assertions)
    print("Classification breakdown:")
    for c in CLASSIFICATION_VALUES:
        print(f"  {c:>12}: {by_class.get(c, 0)}")
    print(f"Output: {OUT_FILE.relative_to(PROJECT_ROOT)}")


def main() -> int:
    test_build_pages_1_4()
    return 0


if __name__ == "__main__":
    sys.exit(main())
