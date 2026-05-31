from __future__ import annotations

import argparse
import base64
import csv
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import anthropic
from anthropic.types import DocumentBlockParam, TextBlockParam
from pydantic import BaseModel, ConfigDict, Field
from tqdm import tqdm

REPO_ROOT = Path(__file__).resolve().parents[3]
GENERATOR_DIR = Path(__file__).resolve().parent
SYSTEM_PROMPT_PATH = GENERATOR_DIR / "GENERATOR_PROMPT.md"
QUESTIONS_PATH = REPO_ROOT / "docs" / "eval" / "questions.csv"
CONTEXT_DIR = REPO_ROOT / "docs" / "eval" / "context"
DEFAULT_OUT_DIR = GENERATOR_DIR / ".cache"

DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_MAX_TOKENS = 8192


class MetaEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    value: str


class IdentifiedPosition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    oz: str = Field(description="The OZ (Ordnungszahl) of the position, e.g. '01.03.0001'.")
    category: str
    description: str
    quantity: float = Field(description="Numeric quantity only, without the unit.")
    unit: str = Field(description="The unit of the quantity, e.g. 'm3', 'm2', 't', 'Stk'.")
    oz_metadata: list[MetaEntry] = Field(
        description="Free-form metadata as key/value pairs, e.g. key='billing_type', value='TA'."
    )


class AggregationAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    reasoning_note: str | None = None
    identified_positions: list[IdentifiedPosition] | None = None
    total: float | None = None
    excluded_positions: list[str] | None = None
    context: list[str] = Field(
        description="Source document/page references, e.g. 'P22039_LV2.pdf::Seite_37'."
    )


class GroundTruthAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str
    question: str
    answer: str | AggregationAnswer = Field(
        description="A plain string for simple lookups, or a structured object for aggregations."
    )
    context: list[str] = Field(
        description="Source document/page references, e.g. 'P22039_HVA_111.pdf::Seite_1'."
    )


IdentifiedPosition.model_rebuild()
AggregationAnswer.model_rebuild()
GroundTruthAnswer.model_rebuild()


def load_api_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key
    env_path = REPO_ROOT / ".env"
    if env_path.is_file():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, _, value = line.partition("=")
            if name.strip() == "ANTHROPIC_API_KEY":
                return value.strip().strip("\"'")
    sys.exit("ANTHROPIC_API_KEY not found in environment or repo-root .env")


def read_questions() -> list[dict[str, str]]:
    with QUESTIONS_PATH.open(encoding="utf-8", newline="") as f:
        return [row for row in csv.DictReader(f) if row.get("Question")]


def discover_projects(only: str | None) -> list[Path]:
    folders = sorted(p for p in CONTEXT_DIR.iterdir() if p.is_dir())
    if only:
        folders = [p for p in folders if p.name == only]
        if not folders:
            sys.exit(f"Project folder '{only}' not found under {CONTEXT_DIR}")
    return folders


def build_document_blocks(folder: Path) -> list[DocumentBlockParam]:
    pdfs = sorted(folder.glob("*.pdf"))
    blocks: list[DocumentBlockParam] = []
    for index, pdf in enumerate(pdfs):
        data = base64.standard_b64encode(pdf.read_bytes()).decode("ascii")
        block: DocumentBlockParam = {
            "type": "document",
            "source": {"type": "base64", "media_type": "application/pdf", "data": data},
            "title": pdf.name,
        }
        if index == len(pdfs) - 1:
            block["cache_control"] = {"type": "ephemeral"}
        blocks.append(block)
    return blocks


def compact_metadata(answer: dict[str, Any]) -> None:
    positions = answer.get("identified_positions")
    if not isinstance(positions, list):
        return
    for position in positions:
        pairs = position.get("oz_metadata")
        if isinstance(pairs, list):
            position["oz_metadata"] = {entry["key"]: entry["value"] for entry in pairs}


def build_record(parsed: GroundTruthAnswer, folder_name: str, row: dict[str, str]) -> dict[str, Any]:
    answer = parsed.answer
    answer_dump: Any = answer.model_dump() if isinstance(answer, AggregationAnswer) else answer
    if isinstance(answer_dump, dict):
        compact_metadata(answer_dump)
    return {
        "QuestionID": row["QuestionID"],
        "QuestionCategory": row["QuestionCategory"],
        "QuestionType": row["QuestionType"],
        "project_id": folder_name,
        "question": row["Question"],
        "answer": answer_dump,
        "context": parsed.context,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate ground-truth answers for eval questions.")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    parser.add_argument("--project", default=None, help="Restrict to one context folder, e.g. P22039.")
    parser.add_argument("--limit", type=int, default=None, help="Cap the number of questions.")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args()

    client = anthropic.Anthropic(api_key=load_api_key())
    system_prompt = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    system: list[TextBlockParam] = [
        {"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}
    ]

    questions = read_questions()
    if args.limit is not None:
        questions = questions[: args.limit]
    folders = discover_projects(args.project)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.out_dir / f"{datetime.now():%Y%m%d_%H%M%S}_truth.json"

    results: list[dict[str, Any]] = []
    total_calls = len(folders) * len(questions)
    with tqdm(total=total_calls, desc="answering") as bar:
        for folder in folders:
            documents = build_document_blocks(folder)
            for row in questions:
                bar.set_postfix_str(f"{folder.name} {row['QuestionID']}")
                try:
                    response = client.messages.parse(
                        model=args.model,
                        max_tokens=args.max_tokens,
                        temperature=0.0,
                        system=system,
                        messages=[
                            {
                                "role": "user",
                                "content": [*documents, {"type": "text", "text": row["Question"]}],
                            }
                        ],
                        output_format=GroundTruthAnswer,
                    )
                    parsed = response.parsed_output
                    if parsed is None:
                        raise ValueError("model returned no parsed output")
                    results.append(build_record(parsed, folder.name, row))
                except Exception as exc:  # noqa: BLE001 - record and continue across the run
                    results.append(
                        {
                            "QuestionID": row["QuestionID"],
                            "QuestionCategory": row["QuestionCategory"],
                            "QuestionType": row["QuestionType"],
                            "project_id": folder.name,
                            "question": row["Question"],
                            "error": str(exc),
                        }
                    )
                out_path.write_text(
                    json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8"
                )
                bar.update(1)

    errors = sum(1 for r in results if "error" in r)
    print(f"Wrote {len(results)} records ({errors} errors) to {out_path}")


if __name__ == "__main__":
    main()
