"""Run LV extraction against a real LV PDF and print the parsed items.

For iterating on the lv_extraction prompt in isolation: it reads the PDF straight off
disk, runs the common extraction + line-numbered rendering, calls the seeded
LV_EXTRACTION prompt, and prints each resolved item plus any validation warnings. It
reads the current prompt version and persists the prompt call's usage + execution log to
Postgres (via the shared client factory).

    python -m scripts.run_lv_extraction eval/context/P0372026/P0372026_LV.pdf

Seed the prompt first with `python -m scripts.seed.prompts`."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from uuid import uuid4

from shared.clients.factory import build_llm_client, build_telemetry_sinks
from shared.config import settings
from shared.db.engine import make_engine
from shared.models.source_line import NewSourceLine, SourceLine
from shared.repositories.prompt_versions import PromptVersionRepository
from shared.services.ingestion.extraction import extract_source_lines
from shared.services.ingestion.lv import postprocess
from shared.services.ingestion.lv.rendering import render_line_numbered
from shared.services.prompt_runner import PromptRunner


async def main(pdf_path: str) -> None:
    source_lines_new = extract_source_lines(Path(pdf_path).read_bytes(), uuid4())
    # extract_source_lines returns NewSourceLine; the pure stages need SourceLine fields
    # (a uuid per line) to slice from, so wrap them with synthetic uuids for this dry
    # run.
    source_lines = [_as_source_line(line) for line in source_lines_new]
    rendered, kept = render_line_numbered(source_lines)
    print(f"{len(source_lines)} source lines, {len(kept)} after furniture strip")

    engine = make_engine(settings.database_url, pool_size=2, application_name="run-lv")
    llm = build_llm_client(build_telemetry_sinks(engine))
    try:
        async with engine.connect() as conn:
            runner = PromptRunner(PromptVersionRepository(conn), llm)
            extraction = await runner.run_lv_extraction(rendered)
    finally:
        await llm.aclose()
        await engine.dispose()

    result = postprocess.run(extraction, source_lines)
    for item in result.items:
        body = (item.langtext_resolved or item.langtext).replace("\n", " ")
        print(f"{item.oz:<10} {item.einheit:<6} {str(item.menge):>10}  {body[:80]}")
    if result.warnings:
        print(f"\n{len(result.warnings)} warning(s):")
        for warning in result.warnings:
            print(f"  - {warning}")


def _as_source_line(new_line: NewSourceLine) -> SourceLine:
    return SourceLine(source_line_uuid=uuid4(), **new_line.model_dump())


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))
