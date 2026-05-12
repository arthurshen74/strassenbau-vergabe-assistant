#!/usr/bin/env python3
"""Transcribe a German PDF page-by-page (Sonnet 4.6 vision) and translate each
paragraph to English (Opus 4.7), writing a flat JSON array of paragraph records.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import statistics
import sys
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from pdf2image import convert_from_path
from tqdm import tqdm

import anthropic

EXTRACT_MODEL = "claude-sonnet-4-6"
TRANSLATE_MODEL = "claude-opus-4-7"
EXTRACT_MAX_TOKENS = 16000
TRANSLATE_MAX_TOKENS = 4096
RETRY_DELAYS = (1, 4, 16)


def die(msg: str, code: int = 1) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def call_with_retry(fn, *, what: str):
    last_exc: Exception | None = None
    for attempt, delay in enumerate((0, *RETRY_DELAYS)):
        if delay:
            time.sleep(delay)
        try:
            return fn()
        except (anthropic.APIError, anthropic.RateLimitError) as exc:
            last_exc = exc
            print(f"  retry {attempt + 1}/{len(RETRY_DELAYS)} for {what}: {exc}", file=sys.stderr)
    raise RuntimeError(f"giving up on {what} after {len(RETRY_DELAYS)} retries: {last_exc}")


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
                 total: int, system: str, tool_schema: dict) -> tuple[list[dict], float]:
    b64 = base64.standard_b64encode(image_path.read_bytes()).decode("ascii")
    user_content = [
        {
            "type": "image",
            "source": {"type": "base64", "media_type": "image/png", "data": b64},
        },
        {
            "type": "text",
            "text": f"This is page {page_num} of {total}. Extract all paragraphs.",
        },
    ]
    t0 = time.perf_counter()
    response = call_with_retry(
        lambda: client.messages.create(
            model=EXTRACT_MODEL,
            temperature=0.0,
            max_tokens=EXTRACT_MAX_TOKENS,
            system=system,
            tools=[tool_schema],
            tool_choice={"type": "tool", "name": tool_schema["name"]},
            messages=[{"role": "user", "content": user_content}],
        ),
        what=f"extract page {page_num}",
    )
    elapsed = time.perf_counter() - t0
    payload = extract_tool_input(response, tool_schema["name"], where=f"page {page_num}")
    paragraphs = payload.get("paragraphs") or []
    if not isinstance(paragraphs, list):
        raise RuntimeError(f"page {page_num}: paragraphs is not a list")
    return paragraphs, elapsed


def translate_paragraph(client: anthropic.Anthropic, text: str, system: str,
                        tool_schema: dict, *, where: str) -> tuple[str, float]:
    t0 = time.perf_counter()
    response = call_with_retry(
        lambda: client.messages.create(
            model=TRANSLATE_MODEL,
            temperature=0.0,
            max_tokens=TRANSLATE_MAX_TOKENS,
            system=system,
            tools=[tool_schema],
            tool_choice={"type": "tool", "name": tool_schema["name"]},
            messages=[{"role": "user", "content": text}],
        ),
        what=f"translate {where}",
    )
    elapsed = time.perf_counter() - t0
    payload = extract_tool_input(response, tool_schema["name"], where=where)
    translation = payload.get("translation")
    if not isinstance(translation, str):
        raise RuntimeError(f"{where}: translation field missing or not a string")
    return translation, elapsed


def fmt_stats(name: str, samples: list[float]) -> str:
    if not samples:
        return f"{name}: (no samples)"
    return (
        f"{name}: n={len(samples)} "
        f"mean={statistics.mean(samples):.2f}s "
        f"median={statistics.median(samples):.2f}s "
        f"min={min(samples):.2f}s max={max(samples):.2f}s"
    )


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

    # Phase 1: extract.
    paragraphs: list[dict] = []
    extract_times: list[float] = []
    for i, image_path in enumerate(tqdm(image_paths, desc="extract", unit="page"), start=1):
        page_paragraphs, elapsed = extract_page(
            client, image_path, i, total_pages, transcribe_prompt, extract_tool
        )
        extract_times.append(elapsed)
        paragraphs.extend(page_paragraphs)

    extracted_count = len(paragraphs)
    print(f"Extracted {extracted_count} paragraph(s) across {total_pages} page(s).")

    # Phase 2: translate.
    translate_times: list[float] = []
    translated_count = 0
    for para in tqdm(paragraphs, desc="translate", unit="para"):
        where = f"p.{para.get('page')}/¶{para.get('paragraph')}"
        translation, elapsed = translate_paragraph(
            client, para["text"], translate_prompt, translate_tool, where=where
        )
        translate_times.append(elapsed)
        para["translation"] = translation
        translated_count += 1

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
    print(f"Output:                {args.output_file_path}")
    print(f"Pages processed:       {total_pages}")
    print(f"Paragraphs extracted:  {extracted_count}")
    print(f"Paragraphs translated: {translated_count}")
    if extracted_count != translated_count:
        print("WARNING: extracted/translated paragraph counts differ!", file=sys.stderr)
    print(f"Total wall time:       {wall:.1f}s")
    print(fmt_stats("Extract latency  ", extract_times))
    print(fmt_stats("Translate latency", translate_times))
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
