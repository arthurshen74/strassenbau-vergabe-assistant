"""Controlled value sets shared across domain models, Core table CHECKs, and the ES index.

These enums are the single source of truth for every discriminator in the data model; both the
write side (table constraints, indexing) and the read side (queries, filters) import the same
member rather than re-typing the literal.
"""

from __future__ import annotations

from enum import StrEnum


class DocumentType(StrEnum):
    LV_DOCUMENT = "LV_DOCUMENT"
    PROSE_DOCUMENT = "PROSE_DOCUMENT"


class SourceDocType(StrEnum):
    LV_ITEM = "LV_ITEM"
    DOCUMENT = "DOCUMENT"


class RetrievalModality(StrEnum):
    SIMPLE = "SIMPLE"
    PLUS = "PLUS"


class IngestStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class PromptType(StrEnum):
    DISPATCHER = "dispatcher"
    PROJECT_CHAT = "project_chat"
    AGGREGATE_LV_MEMBERSHIP = "aggregate_lv_membership"
    MULTI_QUESTION_GENERATOR = "multi_question_generator"
    LV_EXTRACTION = "lv_extraction"
    CONVERSATION_NAME = "conversation_name"
    # ekt_calculator is a conversation discriminator (a position chat that owns a calculator run),
    # not a seeded prompt; the position chat itself runs on PROJECT_CHAT. It is grouped in
    # CONVERSATION_DISCRIMINATORS below. The ekt_* below are the EKT calculation graph's structured
    # LLM prompts (shared/services/calculator/llm_calls.py).
    EKT_CALCULATOR = "ekt_calculator"
    # retired — kept for historical rows: the rezept_autor harness is deleted (the recipe compiler
    # is the katalog_chat agent + rezept_entwurf_speichern); existing conversations with this
    # discriminator must stay parseable, but run_turn treats them as not continuable.
    REZEPT_AUTOR = "rezept_autor"
    # katalog_chat is a conversation discriminator (a catalog chat that owns a create_agent tool
    # loop over the persisted Katalog); grouped below. Its system prompt is the SEEDED
    # katalog_handbuch prompt (below) — this mirrors the EKT_CALCULATOR discriminator + ekt_* seeded
    # prompts pattern.
    KATALOG_CHAT = "katalog_chat"
    # kalkulation_v2 prompts (the live graph).
    EKT_LEISTUNG_CLASSIFY = "ekt_leistung_classify"
    EKT_CHAT_VALUES = "ekt_chat_values"
    EKT_LANGTEXT_EXTRACT = "ekt_langtext_extract"
    EKT_OUTPUT_NARRATE = "ekt_output_narrate"
    # Dedicated synthesis over hybrid-RAG chunks for one project context global at a time.
    PROJECT_CONTEXT_RESOLVE = "project_context_resolve"
    # The katalog_chat agent's system prompt (the Katalog-Handbuch) — a seeded, editable/versioned
    # prompt loaded via get_latest, so the recipe-compiler eval measures the live prompt version.
    KATALOG_HANDBUCH = "katalog_handbuch"


# PromptType members that only DISCRIMINATE which conversation / StateGraph agent owns a
# conversation (they land in conversations.prompt_type) rather than naming a *seeded* prompt. They
# ship no .prompt file and are never seeded or loaded as prompts. When you stand up a new StateGraph
# and tag its conversations with a new member, add it here so the seed-coverage test does not require
# a .prompt file for it. See ADDING_A_PROMPT_TYPE.md ("StateGraph / conversation discriminators").
CONVERSATION_DISCRIMINATORS: frozenset[PromptType] = frozenset(
    {PromptType.EKT_CALCULATOR, PromptType.REZEPT_AUTOR, PromptType.KATALOG_CHAT}
)


class CalculationStatus(StrEnum):
    """Lifecycle of an ekt_calculator conversation's graph run."""

    # Created and shown as a chat gate; the graph has not started. The user can discuss the position
    # (project chat) or ask to run it, which advances to RUNNING.
    AWAITING_START = "awaiting_start"
    RUNNING = "running"
    AWAITING_INPUT = "awaiting_input"
    COMPLETE = "complete"
    FAILED = "failed"


class VariableCorrectionReason(StrEnum):
    """Why a Kalkulator overrode a proposed variable value at Gate B.

    The tag governs eval validity: only model-error reasons count against extraction accuracy;
    KALKULATOR_ERMESSEN is expert preference (the model was not wrong), and KONTEXT_FEHLT is a
    data gap, so both are excluded from the model's score and tracked separately.
    """

    FALSCHER_WERT = "falscher_wert"            # model misread the value (model error)
    FALSCHE_QUELLE = "falsche_quelle"          # value was findable but missed / wrong provenance (model error)
    EINHEIT = "einheit"                        # unit / conversion mistake (model error)
    KONTEXT_FEHLT = "kontext_fehlt"            # value not in the documents (data gap, not a model error)
    KALKULATOR_ERMESSEN = "kalkulator_ermessen"  # expert judgement / risk buffer (not a model error)
    SONSTIGES = "sonstiges"                    # other (see note)


class UsageOperation(StrEnum):
    CHAT = "CHAT"
    EMBEDDING = "EMBEDDING"
    RERANK = "RERANK"


class MessageKind(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    FUNCTION_CALL = "function_call"
    FUNCTION_CALL_OUTPUT = "function_call_output"


class ContextQuelle(StrEnum):
    """Provenance of a project context value version (the `quelle` column)."""

    RAG = "rag"        # resolved from retrieved documents + synthesis
    HITL = "hitl"      # user override / confirmation
    ROUTING = "routing"  # derived by routing (e.g. entfernung_deponie_km)


class ContextStatus(StrEnum):
    """Geocoding outcome for a location context value (the `status` column)."""

    AUFGELOEST = "aufgeloest"        # geocoded to coordinates
    UNSICHER = "unsicher"            # geocoded with low confidence
    FEHLGESCHLAGEN = "fehlgeschlagen"  # could not be geocoded


class RagQuestionType(StrEnum):
    """Reasoning shape of a RAG reference question (mirrors eval/questions.csv QuestionType)."""

    LOOKUP = "lookup"                              # single fact from one place
    AGGREGATION = "aggregation"                    # sum/count over LV positions
    MULTI_HOP = "multi_hop"                        # answer spans several places
    CONSTRAINT_SURFACING = "constraint_surfacing"  # find the applicable constraint/clause
    CROSS_DOC_CONDITIONAL = "cross_doc_conditional"  # condition in one doc, value in another


class RagQuestionCategory(StrEnum):
    """Which role would ask the question."""

    KALKULATOR = "kalkulator"
    BAULEITER = "bauleiter"


class EvalRunKind(StrEnum):
    """Which grader an eval run executes. rag_* are reserved for the RAG evals (Phase 6)."""

    CALCULATOR_GOLD = "calculator_gold"    # re-run + grade extraction vs calculation_ground_truth
    CHAT_VALUES = "chat_values"            # replay EKT_CHAT_VALUES over authored fixtures
    RAG_RETRIEVAL = "rag_retrieval"        # retrieval metrics vs rag_ground_truth refs
    RAG_ANSWERS = "rag_answers"            # answer correctness/faithfulness vs rag_ground_truth


class EvalRunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
