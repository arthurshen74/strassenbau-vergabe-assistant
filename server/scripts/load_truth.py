from __future__ import annotations

import argparse
import asyncio
import json
import re
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from shared.config import settings
from shared.db.engine import make_engine
from shared.domain.eval_item import AnswerType, NewEvalItem, TestType
from shared.domain.project import NewProject
from shared.domain.question import NewQuestion, QuestionCategory, QuestionType
from shared.repositories.eval_items import EvalItemRepository
from shared.repositories.projects import ProjectRepository
from shared.repositories.questions import QuestionRepository

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = REPO_ROOT / "docs" / "eval" / "truth.json"
DEFAULT_PROJECTS = REPO_ROOT / "docs" / "eval" / "projects.json"

CATEGORY_MAP = {"Calculator": QuestionCategory.CALCULATOR, "Bauleiter": QuestionCategory.BAULEITER}
TYPE_MAP = {
    "Lookup": QuestionType.LOOKUP,
    "Aggregation": QuestionType.AGGREGATION,
    "ConstraintSurfacing": QuestionType.CONSTRAINT_SURFACING,
    "CrossDocConditional": QuestionType.CROSS_DOC_CONDITIONAL,
    "MultiHop": QuestionType.MULTI_HOP,
}

HVA_FORM_MAP = {
    "101": "Angebotsaufforderung",
    "111": "Angebotsaufforderung",
    "131": "BVB",
    "132": "BVB",
}

_YES = {"ja", "yes"}
_NO = {"nein", "no"}


def normalize_answer_text(answer: Any) -> str:
    if isinstance(answer, str):
        return answer
    if isinstance(answer, dict):
        return str(answer.get("text", ""))
    return str(answer)


def parse_yes_no(text: str) -> bool | None:
    match = re.match(r"[^A-Za-zÄÖÜäöü]*([A-Za-zÄÖÜäöü]+)", text)
    if not match:
        return None
    word = match.group(1).lower()
    if word in _YES:
        return True
    if word in _NO:
        return False
    return None


def classify_answer(qtype: QuestionType, answer: Any) -> tuple[AnswerType, Any]:
    if qtype == QuestionType.AGGREGATION and isinstance(answer, dict):
        total = answer.get("total")
        if isinstance(total, (int, float)) and not isinstance(total, bool):
            return AnswerType.NUMERICAL, float(total)
    if qtype == QuestionType.CONSTRAINT_SURFACING:
        verdict = parse_yes_no(normalize_answer_text(answer))
        if verdict is not None:
            return AnswerType.YES_NO, verdict
    return AnswerType.FACTUAL, normalize_answer_text(answer)


def resolve_doc_type(context_entry: str, project_id: str, unknown: set[str]) -> str:
    filename = context_entry.split("::", 1)[0]
    token = filename[:-4] if filename.lower().endswith(".pdf") else filename
    prefix = f"{project_id}_"
    if token.startswith(prefix):
        token = token[len(prefix):]
    upper = token.upper()
    if "ZTV" in upper:
        return "ZTV"
    if "BB" in upper:
        return "Baubeschreibung"
    if "LV" in upper:
        return "LV"
    digits = re.search(r"\d+", token)
    if digits and digits.group(0) in HVA_FORM_MAP:
        return HVA_FORM_MAP[digits.group(0)]
    unknown.add(token)
    return token


def doc_types_for(context: list[str], project_id: str, unknown: set[str]) -> list[str]:
    seen: list[str] = []
    for entry in context:
        identifier = resolve_doc_type(entry, project_id, unknown)
        if identifier not in seen:
            seen.append(identifier)
    return seen


def build_eval_items(
    record: dict[str, Any],
    *,
    question_uuid: UUID,
    project_uuid: UUID,
    qtype: QuestionType,
    numerical_tolerance: float,
    unknown: set[str],
) -> list[NewEvalItem]:
    items: list[NewEvalItem] = []

    answer_type, expected = classify_answer(qtype, record["answer"])
    items.append(
        NewEvalItem(
            question_uuid=question_uuid,
            project_uuid=project_uuid,
            test_type=TestType.ANSWER_CORRECTNESS,
            answer_type=answer_type,
            expected_result=expected,
            numerical_tolerance=(
                numerical_tolerance if answer_type == AnswerType.NUMERICAL else None
            ),
        )
    )

    doc_types = doc_types_for(record.get("context", []), record["project_id"], unknown)
    if doc_types:
        items.append(
            NewEvalItem(
                question_uuid=question_uuid,
                project_uuid=project_uuid,
                test_type=TestType.CONTEXT_RETRIEVAL,
                expected_result=doc_types,
            )
        )
    else:
        print(f"  WARN {record['QuestionID']}: no context -> skipping ContextRetrieval item")
    return items


async def resolve_project_uuid(
    conn: AsyncConnection,
    project_id: str,
    projects_meta: dict[str, dict[str, Any]],
    *,
    create: bool,
) -> UUID:
    meta = projects_meta.get(project_id)
    repo = ProjectRepository(conn)
    if meta is not None:
        existing = await repo.get_by_external_id(meta["vergabe_stelle"], project_id)
        if existing is not None:
            return existing.project_uuid
        if not create:
            print(f"  would create project {project_id} ({meta['project_name']})")
            return UUID(int=0)
        created = await repo.add(
            NewProject(
                project_id=project_id,
                project_name=meta["project_name"],
                vergabe_stelle=meta["vergabe_stelle"],
                project_location=meta["location"],
            )
        )
        print(f"  created project {project_id} ({meta['project_name']})")
        return created.project_uuid
    raise SystemExit(
        f"project_id '{project_id}' is not in projects.json and could not be resolved; "
        f"add it to {DEFAULT_PROJECTS.name} or seed it first."
    )


async def reset_project(conn: AsyncConnection, project_uuid: UUID) -> tuple[int, int]:
    eval_repo = EvalItemRepository(conn)
    question_repo = QuestionRepository(conn)
    items = await eval_repo.list_by_project(project_uuid)
    question_uuids = {item.question_uuid for item in items}
    for item in items:
        await eval_repo.delete(item.eval_item_uuid)
    deleted_questions = 0
    for question_uuid in question_uuids:
        if not await eval_repo.list_by_question(question_uuid):
            if await question_repo.delete(question_uuid):
                deleted_questions += 1
    return len(items), deleted_questions


async def run(
    conn: AsyncConnection,
    records: list[dict[str, Any]],
    projects_meta: dict[str, dict[str, Any]],
    *,
    numerical_tolerance: float,
    dry_run: bool,
) -> None:
    question_repo = QuestionRepository(conn)
    eval_repo = EvalItemRepository(conn)
    unknown: set[str] = set()

    project_ids = sorted({r["project_id"] for r in records})
    project_uuids: dict[str, UUID] = {}
    print("Projects:")
    for project_id in project_ids:
        project_uuids[project_id] = await resolve_project_uuid(
            conn, project_id, projects_meta, create=not dry_run
        )

    if not dry_run:
        print("Reset:")
        for project_id in project_ids:
            removed_items, removed_questions = await reset_project(conn, project_uuids[project_id])
            print(f"  {project_id}: removed {removed_items} eval_items, {removed_questions} questions")

    counts = {"questions": 0, "answer_correctness": 0, "context_retrieval": 0}
    print("Loading:")
    for record in records:
        qtype = TYPE_MAP[record["QuestionType"]]
        category = CATEGORY_MAP[record["QuestionCategory"]]
        project_uuid = project_uuids[record["project_id"]]

        if dry_run:
            answer_type, expected = classify_answer(qtype, record["answer"])
            doc_types = doc_types_for(record.get("context", []), record["project_id"], unknown)
            preview = expected if answer_type != AnswerType.FACTUAL else f"{str(expected)[:60]}..."
            print(
                f"  {record['QuestionID']}: {category.value}/{qtype.value} "
                f"-> AnswerCorrectness[{answer_type.value}]={preview!r}; "
                f"ContextRetrieval={doc_types or 'SKIP'}"
            )
            counts["questions"] += 1
            counts["answer_correctness"] += 1
            counts["context_retrieval"] += 1 if doc_types else 0
            continue

        question = await question_repo.add(
            NewQuestion(
                question_category=category,
                question_type=qtype,
                question_text=record["question"],
            )
        )
        counts["questions"] += 1
        for item in build_eval_items(
            record,
            question_uuid=question.question_uuid,
            project_uuid=project_uuid,
            qtype=qtype,
            numerical_tolerance=numerical_tolerance,
            unknown=unknown,
        ):
            await eval_repo.add(item)
            counts[item.test_type.value] += 1

    if unknown:
        print(f"WARN unmapped doc tokens (passed through as-is): {sorted(unknown)}")
    label = "Planned" if dry_run else "Loaded"
    print(
        f"{label}: {counts['questions']} questions, "
        f"{counts['answer_correctness']} AnswerCorrectness, "
        f"{counts['context_retrieval']} ContextRetrieval"
    )


async def main() -> None:
    parser = argparse.ArgumentParser(description="Load ground-truth JSON into the eval database.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Path to a truth.json.")
    parser.add_argument("--projects", type=Path, default=DEFAULT_PROJECTS)
    parser.add_argument("--numerical-tolerance", type=float, default=0.0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    records: list[dict[str, Any]] = json.loads(args.input.read_text(encoding="utf-8"))
    projects_list: list[dict[str, Any]] = json.loads(args.projects.read_text(encoding="utf-8"))
    projects_meta = {p["project_id"]: p for p in projects_list}

    engine: AsyncEngine = make_engine(
        settings.database_url, pool_size=2, application_name="load-truth"
    )
    try:
        if args.dry_run:
            async with engine.connect() as conn:
                await run(
                    conn,
                    records,
                    projects_meta,
                    numerical_tolerance=args.numerical_tolerance,
                    dry_run=True,
                )
        else:
            async with engine.begin() as conn:
                await run(
                    conn,
                    records,
                    projects_meta,
                    numerical_tolerance=args.numerical_tolerance,
                    dry_run=False,
                )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
