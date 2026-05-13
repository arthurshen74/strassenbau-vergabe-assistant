#!/usr/bin/env python3
"""Transcribe a German PDF page-by-page (Sonnet 4.6 vision) and translate each
paragraph to English (Opus 4.7), writing a flat JSON array of paragraph records.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import random
import re
import shutil
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from pdf2image import convert_from_path
from tqdm import tqdm

import anthropic

EXTRACT_MODEL = "claude-sonnet-4-6"
TRANSLATE_MODELS = ("claude-opus-4-7", "claude-opus-4-6", "claude-sonnet-4-6")
SUBSTANTIVE_START_MODEL = "claude-sonnet-4-6"
EXTRACT_MAX_TOKENS = 16000
TRANSLATE_MAX_TOKENS = 4096
RETRY_BASE_DELAY = 1.0
RETRY_MAX_DELAY = 120.0
RETRY_MAX_ATTEMPTS = 8


def die(msg: str, code: int = 1) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def repair_unescaped_quotes(s: str) -> str:
    """Escape unescaped ASCII `"` that appear inside JSON string values.

    Walks character by character. When inside a string and we hit `"`,
    look ahead past whitespace: if the next non-space char is `:`, `}`,
    `]`, or end-of-input, it's a structural close. If it's `,`, peek past
    the comma to see if the next non-space char is `"`, `{`, or `[`
    (start of next field/element) — if so, structural; otherwise
    embedded. Anything else after the quote → embedded → escape it.
    Assumes a schema where string values aren't followed by raw scalars
    in the same array — true for our paragraphs schema.
    """
    out: list[str] = []
    i = 0
    in_string = False
    while i < len(s):
        c = s[i]
        if not in_string:
            out.append(c)
            if c == '"':
                in_string = True
            i += 1
            continue
        if c == "\\":
            out.append(c)
            if i + 1 < len(s):
                out.append(s[i + 1])
                i += 2
            else:
                i += 1
            continue
        if c == '"':
            j = i + 1
            while j < len(s) and s[j] in " \t\n\r":
                j += 1
            if j >= len(s) or s[j] in ":}]":
                out.append(c)
                in_string = False
                i += 1
                continue
            if s[j] == ",":
                k = j + 1
                while k < len(s) and s[k] in " \t\n\r":
                    k += 1
                if k >= len(s) or s[k] in '"{[':
                    out.append(c)
                    in_string = False
                    i += 1
                    continue
            out.append('\\"')
            i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


def call_with_retry(fn, *, what: str):
    """Run `fn`, retrying API errors with exponential backoff + equal jitter
    (delay in [base/2, base], base = min(MAX_DELAY, BASE * 2**attempt)).
    """
    last_exc: Exception | None = None
    for attempt in range(RETRY_MAX_ATTEMPTS):
        try:
            return fn()
        except (anthropic.APIError, anthropic.RateLimitError) as exc:
            last_exc = exc
            if attempt == RETRY_MAX_ATTEMPTS - 1:
                break
            base = min(RETRY_MAX_DELAY, RETRY_BASE_DELAY * (2 ** attempt))
            delay = base / 2 + random.uniform(0, base / 2)
            print(
                f"  retry {attempt + 1}/{RETRY_MAX_ATTEMPTS} for {what} "
                f"in {delay:.1f}s: {exc}",
                file=sys.stderr,
            )
            time.sleep(delay)
    raise RuntimeError(
        f"giving up on {what} after {RETRY_MAX_ATTEMPTS} attempts: {last_exc}"
    )


def extract_tool_input(response, tool_name: str, *, where: str) -> dict[str, Any]:
    for block in response.content:
        if getattr(block, "type", None) == "tool_use" and block.name == tool_name:
            return block.input
    raise RuntimeError(f"no tool_use block named {tool_name!r} in response for {where}")


def render_pages(pdf_path: Path, cache_dir: Path) -> list[Path]:
    if shutil.which("pdftoppm") is None:
        die("`pdftoppm` not found on PATH. Install poppler: `brew install poppler`.")
    cache_dir.mkdir(parents=True, exist_ok=True)

    existing = sorted(cache_dir.glob("page_*.png"))
    if existing:
        print(f"Using cached page images in {cache_dir} ({len(existing)} pages).")
        return existing

    print(f"Rendering {pdf_path.name} at 300 DPI to {cache_dir}...")
    raw_paths = convert_from_path(
        str(pdf_path),
        dpi=300,
        fmt="png",
        output_folder=str(cache_dir),
        output_file="page",
        paths_only=True,
    )
    raw_paths = sorted(Path(p) for p in raw_paths)
    pad = max(3, len(str(len(raw_paths))))
    normalized: list[Path] = []
    for i, p in enumerate(raw_paths, start=1):
        target = cache_dir / f"page_{i:0{pad}d}.png"
        if p != target:
            p.rename(target)
        normalized.append(target)
    return normalized


def extract_page(client: anthropic.Anthropic, image_path: Path, page_num: int,
                 total: int, system: str, tool_schema: dict,
                 debug_dir: Path) -> tuple[list[dict], float]:
    b64 = base64.standard_b64encode(image_path.read_bytes()).decode("ascii")
    user_content = [
        {
            "type": "image",
            "source": {"type": "base64", "media_type": "image/png", "data": b64},
        },
        {
            "type": "text",
            "text": (
                f"This is page {page_num} of {total}. Extract all paragraphs. "
                "Return `paragraphs` as a structured JSON array of objects, "
                "not a JSON-encoded string."
            ),
        },
    ]

    def attempt(temperature: float):
        t0 = time.perf_counter()
        response = call_with_retry(
            lambda: client.messages.create(
                model=EXTRACT_MODEL,
                temperature=temperature,
                max_tokens=EXTRACT_MAX_TOKENS,
                system=system,
                tools=[tool_schema],
                tool_choice={"type": "tool", "name": tool_schema["name"]},
                messages=[{"role": "user", "content": user_content}],
            ),
            what=f"extract page {page_num} (temp={temperature})",
        )
        elapsed = time.perf_counter() - t0
        payload = extract_tool_input(response, tool_schema["name"],
                                     where=f"page {page_num}")
        paragraphs = payload.get("paragraphs")
        # Sonnet occasionally emits `paragraphs` as a JSON-encoded string under
        # forced tool use, and the stringified content can contain unescaped
        # `"` inside string values (German typographic quotes, markdown
        # quotes, etc.). Parse strictly first; on failure, escape embedded
        # quotes via state-machine repair and retry.
        if isinstance(paragraphs, str):
            parsed = None
            try:
                parsed = json.loads(paragraphs)
                tqdm.write(
                    f"  page {page_num}: recovered stringified paragraphs "
                    f"array (temp={temperature})"
                )
            except json.JSONDecodeError:
                repaired = repair_unescaped_quotes(paragraphs)
                try:
                    parsed = json.loads(repaired)
                    tqdm.write(
                        f"  page {page_num}: repaired unescaped quotes and "
                        f"parsed stringified paragraphs (temp={temperature})"
                    )
                except json.JSONDecodeError:
                    parsed = None
            if isinstance(parsed, list):
                paragraphs = parsed
        return paragraphs, elapsed, response, payload

    paragraphs, elapsed, response, payload = attempt(0.0)
    if not isinstance(paragraphs, list):
        tqdm.write(
            f"  page {page_num}: temp=0.0 produced {type(paragraphs).__name__}; "
            f"retrying at temp=0.5"
        )
        retry_paragraphs, retry_elapsed, response, payload = attempt(0.5)
        elapsed += retry_elapsed
        if isinstance(retry_paragraphs, list):
            paragraphs = retry_paragraphs

    if not isinstance(paragraphs, list):
        debug_dir.mkdir(parents=True, exist_ok=True)
        err_path = debug_dir / f"page_{page_num:03d}.error.json"
        err_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        raise RuntimeError(
            f"page {page_num}: 'paragraphs' field is {type(paragraphs).__name__} "
            f"(expected list) after temp-bump retry. "
            f"stop_reason={response.stop_reason!r}. "
            f"payload keys={list(payload.keys())}. raw payload dumped to {err_path}"
        )
    return paragraphs, elapsed


def translate_paragraph(client: anthropic.Anthropic, text: str, system: str,
                        tool_schema: dict, models: tuple[str, ...],
                        *, where: str) -> tuple[str, float, str]:
    """Translate text, trying each model in `models` in order. Falls back to
    the next model if one exhausts retries or returns a malformed response.
    Returns (translation, elapsed_seconds, model_used).
    """
    last_exc: Exception | None = None
    for idx, model in enumerate(models):
        try:
            t0 = time.perf_counter()
            response = call_with_retry(
                lambda model=model: client.messages.create(
                    model=model,
                    max_tokens=TRANSLATE_MAX_TOKENS,
                    system=system,
                    tools=[tool_schema],
                    tool_choice={"type": "tool", "name": tool_schema["name"]},
                    messages=[{"role": "user", "content": text}],
                ),
                what=f"translate {where} ({model})",
            )
            elapsed = time.perf_counter() - t0
            payload = extract_tool_input(response, tool_schema["name"], where=where)
            translation = payload.get("translation")
            if not isinstance(translation, str):
                raise RuntimeError(
                    f"{where}: translation field missing or not a string"
                )
            if idx > 0:
                tqdm.write(f"  {where}: succeeded on fallback model {model}")
            return translation, elapsed, model
        except (RuntimeError, anthropic.APIError) as exc:
            last_exc = exc
            if idx < len(models) - 1:
                tqdm.write(
                    f"  {where}: model {model} failed ({exc}); "
                    f"falling back to {models[idx + 1]}"
                )
    raise RuntimeError(
        f"all translation models exhausted for {where}: {last_exc}"
    )


def fmt_stats(name: str, samples: list[float]) -> str:
    if not samples:
        return f"{name}: (no samples)"
    return (
        f"{name}: n={len(samples)} "
        f"mean={statistics.mean(samples):.2f}s "
        f"median={statistics.median(samples):.2f}s "
        f"min={min(samples):.2f}s max={max(samples):.2f}s"
    )


def _normalize_for_match(s: str) -> str:
    """Normalize text for header/footer clustering: trim, lowercase,
    collapse internal whitespace, mask every run of digits with a single
    `_`. No punctuation stripping. Runs must collapse (not per-digit) so
    that single- and double-digit page numbers cluster together
    (`Seite 2 zum Schreiben` and `Seite 10 zum Schreiben` both become
    `seite _ zum schreiben`)."""
    s = s.strip().lower()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"\d+", "_", s)
    return s


def _text_hash(text: str) -> tuple[str, str]:
    """Return (full_hex, prefix16) sha256 of `text`. Prefix used as cache
    filename; full hex stored inside for inspection / future widening."""
    full = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return full, full[:16]


def filter_header_footer(paragraphs: list[dict], total_pages: int
                         ) -> tuple[list[dict], list[dict]]:
    """Drop paragraphs that match repeating header/footer patterns.

    Inspects positions 1, 2, second-to-last, and last on each page. Builds
    a frequency map keyed on the normalized text. Any cluster whose size is
    in {total_pages, total_pages - 1} is treated as a header/footer pattern;
    every paragraph whose normalized text matches a pattern is dropped,
    even if positioned mid-page.

    Returns (kept, dropped). Each dropped dict has an added `_reason` field
    naming the pattern it matched.
    """
    # Group paragraphs by page, preserving original order.
    by_page: dict[int, list[dict]] = defaultdict(list)
    for p in paragraphs:
        by_page[p["page"]].append(p)
    for page in by_page:
        by_page[page].sort(key=lambda x: x["paragraph"])

    # Collect normalized text from positions of interest.
    candidates: dict[str, list[tuple[int, int]]] = defaultdict(list)
    edge_positions: set[tuple[int, int]] = set()
    for page, items in by_page.items():
        if not items:
            continue
        positions: list[int] = []
        positions.append(0)
        if len(items) >= 2:
            positions.append(1)
            positions.append(len(items) - 1)
        if len(items) >= 3:
            positions.append(len(items) - 2)
        for idx in set(positions):
            p = items[idx]
            normalized = _normalize_for_match(p["text"])
            if not normalized:
                continue
            candidates[normalized].append((p["page"], p["paragraph"]))
            edge_positions.add((p["page"], p["paragraph"]))

    # Identify patterns whose cluster size matches the page count (-1).
    patterns: dict[str, int] = {}
    print("Header/footer candidate clusters:")
    for normalized, occurrences in sorted(
        candidates.items(), key=lambda kv: (-len(kv[1]), kv[0])
    ):
        marker = ""
        if len(occurrences) in (total_pages, total_pages - 1):
            marker = " [HEADER/FOOTER PATTERN]"
            patterns[normalized] = len(occurrences)
        sample_positions = ", ".join(f"p{pg}/¶{pa}" for pg, pa in occurrences[:5])
        more = f" ... (+{len(occurrences) - 5} more)" if len(occurrences) > 5 else ""
        print(f"  [{len(occurrences):>2}] {normalized!r}: {sample_positions}{more}{marker}")

    if not patterns:
        print("  (no clusters matched header/footer thresholds)")
        return list(paragraphs), []

    # Drop every paragraph whose normalized text matches a pattern.
    kept: list[dict] = []
    dropped: list[dict] = []
    for p in paragraphs:
        normalized = _normalize_for_match(p["text"])
        if normalized in patterns:
            entry = dict(p)
            entry["_reason"] = f"matches header/footer pattern: {normalized!r}"
            dropped.append(entry)
            if (p["page"], p["paragraph"]) not in edge_positions:
                print(
                    f"  WARN: dropped paragraph p{p['page']}/¶{p['paragraph']} "
                    f"matched a header/footer pattern but appears mid-page "
                    f"(not in positions 1, 2, second-to-last, or last)."
                )
        else:
            kept.append(p)

    print(f"Header/footer filter: dropped {len(dropped)}, kept {len(kept)}.")
    return kept, dropped


def load_cue_phrases(path: Path) -> list[re.Pattern]:
    """Load substantive-start cue phrases from a text file. One regex per
    line; blank lines and `#` comments ignored. Compiled IGNORECASE."""
    if not path.is_file():
        return []
    patterns: list[re.Pattern] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        patterns.append(re.compile(line, re.IGNORECASE))
    return patterns


def find_substantive_start_regex(paragraphs: list[dict],
                                 cues: list[re.Pattern]
                                 ) -> tuple[int, int] | None:
    """Iterate paragraphs in document order; return (page, paragraph) of the
    first whose text matches any cue. Returns None if no match."""
    if not cues:
        return None
    ordered = sorted(paragraphs, key=lambda p: (p["page"], p["paragraph"]))
    for p in ordered:
        text = p.get("text", "")
        for cue in cues:
            if cue.search(text):
                return p["page"], p["paragraph"]
    return None


def find_substantive_start_llm(client: anthropic.Anthropic,
                               paragraphs: list[dict]
                               ) -> tuple[int, int] | None:
    """Ask Sonnet 4.6 to identify the first substantive paragraph. Uses
    assistant-prefill JSON output instead of forced tool use (simpler,
    avoids the stringification quirk we hit on the extraction phase).
    Returns (page, paragraph) or None on parse failure.
    """
    ordered = sorted(paragraphs, key=lambda p: (p["page"], p["paragraph"]))
    lines = []
    for p in ordered:
        snippet = " ".join(p.get("text", "").split())[:200]
        lines.append(f"p{p['page']}/¶{p['paragraph']}: {snippet}")
    user_msg = "\n".join(lines)

    system = (
        "You are reading a German legal pleading. Identify the first "
        "paragraph that begins the substantive factual claims or legal "
        "arguments. Skip headers, addressee blocks, Vorbemerkungen, "
        "Anträge, and Tatbestand summaries. Respond ONLY with a JSON "
        "object of the form {\"page\": N, \"paragraph\": M}."
    )

    response = call_with_retry(
        lambda: client.messages.create(
            model=SUBSTANTIVE_START_MODEL,
            temperature=0.0,
            max_tokens=64,
            system=system,
            stop_sequences=["}"],
            messages=[
                {"role": "user", "content": user_msg},
                {"role": "assistant", "content": '{"page": '},
            ],
        ),
        what="locate substantive start (LLM)",
    )
    # Reassemble the JSON literal: prefill + model output + the stop char.
    text_parts = [b.text for b in response.content if getattr(b, "type", None) == "text"]
    body = "".join(text_parts)
    raw = '{"page": ' + body + "}"
    try:
        parsed = json.loads(raw)
        page = int(parsed["page"])
        paragraph = int(parsed["paragraph"])
        return page, paragraph
    except (json.JSONDecodeError, KeyError, ValueError, TypeError) as exc:
        print(f"  WARN: substantive-start LLM returned unparseable {raw!r}: {exc}",
              file=sys.stderr)
        return None


def filter_before_substantive_start(paragraphs: list[dict],
                                    start: tuple[int, int]
                                    ) -> tuple[list[dict], list[dict]]:
    """Drop paragraphs that come before (start_page, start_paragraph) in
    document order. Returns (kept, dropped)."""
    start_key = start
    kept: list[dict] = []
    dropped: list[dict] = []
    for p in paragraphs:
        if (p["page"], p["paragraph"]) < start_key:
            dropped.append(dict(p))
        else:
            kept.append(p)
    return kept, dropped


def migrate_translation_cache(translations_dir: Path,
                              cache_dir: Path) -> int:
    """One-shot migration from positional cache filenames (`pNNN_paraNNN.json`)
    to hash-keyed filenames. Looks up paragraph text in the per-page
    extraction cache files and writes the new hash entry. Removes the old
    positional file on success. Idempotent.
    """
    if not translations_dir.is_dir():
        return 0
    positional_pattern = re.compile(r"^p(\d{3})_para(\d{3})\.json$")
    page_cache: dict[int, list[dict]] = {}

    migrated = 0
    for entry in sorted(translations_dir.iterdir()):
        if not entry.is_file():
            continue
        m = positional_pattern.match(entry.name)
        if not m:
            continue
        page_num = int(m.group(1))
        para_num = int(m.group(2))

        if page_num not in page_cache:
            page_file = cache_dir / f"page_{page_num:03d}.paragraphs.json"
            if not page_file.is_file():
                print(f"  WARN: cannot migrate {entry.name}: missing {page_file.name}",
                      file=sys.stderr)
                continue
            page_cache[page_num] = json.loads(page_file.read_text(encoding="utf-8"))

        text = None
        for item in page_cache[page_num]:
            if item.get("paragraph") == para_num:
                text = item.get("text")
                break
        if text is None:
            print(f"  WARN: cannot migrate {entry.name}: no paragraph {para_num} "
                  f"in page {page_num} cache", file=sys.stderr)
            continue

        old = json.loads(entry.read_text(encoding="utf-8"))
        full_hex, hash16 = _text_hash(text)
        new_path = translations_dir / f"{hash16}.json"
        if not new_path.is_file():
            new_path.write_text(
                json.dumps(
                    {
                        "hash": full_hex,
                        "text": text,
                        "translation": old.get("translation"),
                        "model": old.get("model"),
                    },
                    indent=2, ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        entry.unlink()
        migrated += 1

    if migrated:
        print(f"Translation cache: migrated {migrated} positional file(s) to hash-keyed format.")
    return migrated


def renumber(paragraphs: list[dict]) -> None:
    """In-place: within each page, renumber `paragraph` starting at 1 by
    original order. Page numbers are not touched."""
    by_page: dict[int, list[dict]] = defaultdict(list)
    for p in paragraphs:
        by_page[p["page"]].append(p)
    for page, items in by_page.items():
        items.sort(key=lambda x: x["paragraph"])
        for new_idx, item in enumerate(items, start=1):
            item["paragraph"] = new_idx


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf_path", type=Path, help="Input PDF file")
    parser.add_argument("output_file_path", type=Path, help="Output JSON file")
    args = parser.parse_args()

    if not args.pdf_path.is_file():
        die(f"PDF not found: {args.pdf_path}")

    load_dotenv()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        die("ANTHROPIC_API_KEY not set in environment or .env")

    script_dir = Path(__file__).resolve().parent
    transcribe_prompt = read_text(script_dir / "transcribe.md")
    translate_prompt = read_text(script_dir / "translate.md")
    extract_tool = read_json(script_dir / "submitExtraction.json")
    translate_tool = read_json(script_dir / "submitTranslation.json")

    pdf_stem = args.pdf_path.stem
    safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", pdf_stem)
    cache_dir = Path(".cache") / safe_stem

    image_paths = render_pages(args.pdf_path, cache_dir)
    total_pages = len(image_paths)
    print(f"{total_pages} page(s) ready.")

    client = anthropic.Anthropic()

    wall_start = time.perf_counter()

    # Phase 1: extract. Cached per-page so reruns skip completed pages.
    paragraphs: list[dict] = []
    extract_times: list[float] = []
    for i, image_path in enumerate(tqdm(image_paths, desc="extract", unit="page"), start=1):
        page_cache = cache_dir / f"page_{i:03d}.paragraphs.json"
        if page_cache.is_file():
            page_paragraphs = json.loads(page_cache.read_text(encoding="utf-8"))
            tqdm.write(f"  page {i}: loaded {len(page_paragraphs)} cached paragraph(s)")
        else:
            page_paragraphs, elapsed = extract_page(
                client, image_path, i, total_pages, transcribe_prompt, extract_tool,
                debug_dir=cache_dir,
            )
            extract_times.append(elapsed)
            page_cache.write_text(
                json.dumps(page_paragraphs, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        paragraphs.extend(page_paragraphs)

    extracted_count = len(paragraphs)
    print(f"Extracted {extracted_count} paragraph(s) across {total_pages} page(s).")

    # Translation cache: migrate any positional files left over from the old
    # numbering scheme to hash-keyed filenames before the translate phase.
    translations_dir = cache_dir / "translations"
    translations_dir.mkdir(parents=True, exist_ok=True)
    migrate_translation_cache(translations_dir, cache_dir)

    # Filter: header/footer.
    paragraphs, dropped_header_footer = filter_header_footer(paragraphs, total_pages)

    # Filter: substantive start (regex fast path → LLM fallback).
    cue_path = script_dir / "substantiveStartPhrases.txt"
    cues = load_cue_phrases(cue_path)
    print(f"Loaded {len(cues)} substantive-start cue phrase(s) from {cue_path.name}.")
    start = find_substantive_start_regex(paragraphs, cues)
    matched_by = "regex" if start else None
    if start is None:
        # TODO: insert HF sentence-transformer middle layer here when use
        # volume justifies it (regex → NLP fuzzy → LLM).
        print("Regex cues did not match; calling LLM to locate substantive start...")
        start = find_substantive_start_llm(client, paragraphs)
        matched_by = "llm" if start else None

    dropped_before_start: list[dict] = []
    if start is not None:
        print(f"Substantive start: p{start[0]}/¶{start[1]} (matched by {matched_by}).")
        paragraphs, dropped_before_start = filter_before_substantive_start(paragraphs, start)
        print(f"Substantive-start filter: dropped {len(dropped_before_start)}, "
              f"kept {len(paragraphs)}.")
    else:
        print("WARN: substantive start not located by regex or LLM; "
              "keeping all paragraphs (fail-open).")

    # Filter audit log.
    audit = {
        "header_footer": [
            {
                "page": d["page"],
                "paragraph": d["paragraph"],
                "reason": d.get("_reason", ""),
                "text": d["text"],
            }
            for d in dropped_header_footer
        ],
        "before_substantive_start": [
            {"page": d["page"], "paragraph": d["paragraph"], "text": d["text"]}
            for d in dropped_before_start
        ],
        "substantive_start": (
            {"page": start[0], "paragraph": start[1], "matched_by": matched_by}
            if start is not None
            else None
        ),
    }
    (cache_dir / "filtered.json").write_text(
        json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # Phase 2: translate. Hash-keyed cache survives renumbering / filter tweaks.
    translate_times: list[float] = []
    translated_count = 0
    for para in tqdm(paragraphs, desc="translate", unit="para"):
        page_num = para.get("page")
        para_num = para.get("paragraph")
        where = f"p.{page_num}/¶{para_num}"
        full_hex, hash16 = _text_hash(para["text"])
        para_cache = translations_dir / f"{hash16}.json"
        translation: str | None = None
        if para_cache.is_file():
            cached = json.loads(para_cache.read_text(encoding="utf-8"))
            if cached.get("text") == para["text"]:
                translation = cached["translation"]
            else:
                # Hash prefix collision (vanishingly unlikely) — treat as miss.
                print(f"  WARN: hash16 collision at {hash16} for {where}; "
                      f"refreshing cache entry.", file=sys.stderr)
        if translation is None:
            translation, elapsed, model_used = translate_paragraph(
                client, para["text"], translate_prompt, translate_tool,
                TRANSLATE_MODELS, where=where,
            )
            translate_times.append(elapsed)
            para_cache.write_text(
                json.dumps(
                    {
                        "hash": full_hex,
                        "text": para["text"],
                        "translation": translation,
                        "model": model_used,
                    },
                    indent=2, ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        para["translation"] = translation
        translated_count += 1

    # Renumber paragraphs per-page (page numbers untouched) before writing.
    renumber(paragraphs)

    # Write output.
    args.output_file_path.parent.mkdir(parents=True, exist_ok=True)
    args.output_file_path.write_text(
        json.dumps(paragraphs, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    wall = time.perf_counter() - wall_start

    # Report.
    print()
    print("=" * 60)
    print(f"Output:                          {args.output_file_path}")
    print(f"Pages processed:                 {total_pages}")
    print(f"Paragraphs extracted:            {extracted_count}")
    print(f"Paragraphs dropped (header/footer):  {len(dropped_header_footer)}")
    print(f"Paragraphs dropped (pre-substantive): {len(dropped_before_start)}")
    print(f"Substantive start matched by:    {matched_by or 'none'}")
    print(f"Paragraphs translated:           {translated_count}")
    if translated_count != extracted_count - len(dropped_header_footer) - len(dropped_before_start):
        print("WARNING: translated count does not match (extracted - dropped)!", file=sys.stderr)
    print(f"Total wall time:                 {wall:.1f}s")
    print(fmt_stats("Extract latency  ", extract_times))
    print(fmt_stats("Translate latency", translate_times))
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
