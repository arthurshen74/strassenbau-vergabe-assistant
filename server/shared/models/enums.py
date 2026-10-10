"""Controlled value sets shared across domain models, Core table CHECKs, and the ES
index.

These enums are the single source of truth for every discriminator in the data model;
both the write side (table constraints, indexing) and the read side (queries, filters)
import the same member rather than re-typing the literal.
"""

from __future__ import annotations

from enum import StrEnum


class DocumentType(StrEnum):
    LV_DOCUMENT = "LV_DOCUMENT"
    PROSE_DOCUMENT = "PROSE_DOCUMENT"
    FORM_DOCUMENT = "FORM_DOCUMENT"


class FormRole(StrEnum):
    """Who fills a Formblatt: issued by the Vergabestelle, or filled by the Bieter."""

    VERGABESTELLE = "vergabestelle"
    BIETER = "bieter"
    UNBEKANNT = "unbekannt"


class SourceDocType(StrEnum):
    LV_ITEM = "LV_ITEM"
    LV_TEXT = "LV_TEXT"
    DOCUMENT = "DOCUMENT"
    FORM = "FORM"


class LVTextKind(StrEnum):
    """Which GAEB carrier an LV text row came from."""

    ADD_TEXT = "ADD_TEXT"  # Zusaetzlicher Text: GAEB 90 T-lines, GAEB XML AddText
    REMARK = "REMARK"  # Hinweistext: GAEB 90 record 20, GAEB XML Remark


class LVTextPlacement(StrEnum):
    """Where a Zusaetzlicher Text sits relative to the BoQ: Vortext or Nachtext."""

    BEFORE_BOQ = "before"
    AFTER_BOQ = "after"


class RetrievalModality(StrEnum):
    SIMPLE = "SIMPLE"
    PLUS = "PLUS"


class IngestStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    # Set at enqueue for a Bieter form; never claimed, requeue ingests it.
    SKIPPED = "skipped"


class ConsoleJobKind(StrEnum):
    """Which queue an ingest-console row comes from."""

    INGEST = "ingest"
    PROJECT_INFO = "project_info"


class PromptType(StrEnum):
    DISPATCHER = "dispatcher"
    PROJECT_CHAT = "project_chat"
    AGGREGATE_LV_MEMBERSHIP = "aggregate_lv_membership"
    MULTI_QUESTION_GENERATOR = "multi_question_generator"
    LV_EXTRACTION = "lv_extraction"
    CONVERSATION_NAME = "conversation_name"
    # ekt_calculator is a conversation discriminator (a position chat that owns a
    # calculator run), not a seeded prompt; the position chat itself runs on
    # PROJECT_CHAT. It is grouped in CONVERSATION_DISCRIMINATORS below. The ekt_* below
    # are the EKT calculation graph's structured LLM prompts
    # (shared/services/calculator/llm_calls.py).
    EKT_CALCULATOR = "ekt_calculator"
    # retired — kept for historical rows: the rezept_autor harness is deleted (the
    # recipe compiler is the katalog_chat agent + rezept_entwurf_speichern); existing
    # conversations with this discriminator must stay parseable, but run_turn treats
    # them as not continuable.
    REZEPT_AUTOR = "rezept_autor"
    # katalog_chat is a conversation discriminator (a catalog chat that owns a
    # create_agent tool loop over the persisted Katalog); grouped below. Its system
    # prompt is the SEEDED katalog_handbuch prompt (below) — this mirrors the
    # EKT_CALCULATOR discriminator + ekt_* seeded prompts pattern.
    KATALOG_CHAT = "katalog_chat"
    # kalkulation_v2 prompts (the live graph).
    EKT_LEISTUNG_CLASSIFY = "ekt_leistung_classify"
    EKT_CHAT_VALUES = "ekt_chat_values"
    EKT_LANGTEXT_EXTRACT = "ekt_langtext_extract"
    EKT_OUTPUT_NARRATE = "ekt_output_narrate"
    # Dedicated synthesis over hybrid-RAG chunks for one project context global at a
    # time.
    PROJECT_CONTEXT_RESOLVE = "project_context_resolve"
    # The katalog_chat agent's system prompt (the Katalog-Handbuch) — a seeded,
    # editable/versioned prompt loaded via get_latest, so the recipe-compiler eval
    # measures the live prompt version.
    KATALOG_HANDBUCH = "katalog_handbuch"
    # One-shot NER misprediction error analysis: categorizes a flag against the closed
    # failure taxonomy and optionally suggests an entity rule. Loaded via get_latest per
    # flag.
    NER_FEHLERANALYSE = "ner_fehleranalyse"
    # Synthesis over hybrid-RAG chunks for one project header field (Projektinfo) at a
    # time.
    PROJECT_INFO_RESOLVE = "project_info_resolve"


# PromptType members that only DISCRIMINATE which conversation / StateGraph agent owns a
# conversation (they land in conversations.prompt_type) rather than naming a *seeded*
# prompt. They ship no .prompt file and are never seeded or loaded as prompts. When you
# stand up a new StateGraph and tag its conversations with a new member, add it here so
# the seed-coverage test does not require a .prompt file for it. See
# ADDING_A_PROMPT_TYPE.md ("StateGraph / conversation discriminators").
CONVERSATION_DISCRIMINATORS: frozenset[PromptType] = frozenset(
    {PromptType.EKT_CALCULATOR, PromptType.REZEPT_AUTOR, PromptType.KATALOG_CHAT}
)


class CalculationStatus(StrEnum):
    """Lifecycle of an ekt_calculator conversation's graph run."""

    # Created and shown as a chat gate; the graph has not started. The user can discuss
    # the position (project chat) or ask to run it, which advances to RUNNING.
    AWAITING_START = "awaiting_start"
    RUNNING = "running"
    AWAITING_INPUT = "awaiting_input"
    COMPLETE = "complete"
    FAILED = "failed"


class VariableCorrectionReason(StrEnum):
    """Why a Kalkulator overrode a proposed variable value at Gate B.

    The tag governs eval validity: only model-error reasons count against extraction
    accuracy; KALKULATOR_ERMESSEN is expert preference (the model was not wrong), and
    KONTEXT_FEHLT is a data gap, so both are excluded from the model's score and tracked
    separately.
    """

    FALSCHER_WERT = "falscher_wert"  # model misread the value (model error)
    # value was findable but missed / wrong provenance (model error)
    FALSCHE_QUELLE = "falsche_quelle"
    EINHEIT = "einheit"  # unit / conversion mistake (model error)
    KONTEXT_FEHLT = (
        "kontext_fehlt"  # value not in the documents (data gap, not a model error)
    )
    KALKULATOR_ERMESSEN = (
        "kalkulator_ermessen"  # expert judgement / risk buffer (not a model error)
    )
    SONSTIGES = "sonstiges"  # other (see note)


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

    RAG = "rag"  # resolved from retrieved documents + synthesis
    HITL = "hitl"  # user override / confirmation
    ROUTING = "routing"  # derived by routing (e.g. entfernung_deponie_km)


class ContextStatus(StrEnum):
    """Geocoding outcome for a location context value (the `status` column)."""

    AUFGELOEST = "aufgeloest"  # geocoded to coordinates
    UNSICHER = "unsicher"  # geocoded with low confidence
    FEHLGESCHLAGEN = "fehlgeschlagen"  # could not be geocoded


class RagQuestionType(StrEnum):
    """Reasoning shape of a RAG reference question (mirrors eval/questions.csv
    QuestionType)."""

    LOOKUP = "lookup"  # single fact from one place
    AGGREGATION = "aggregation"  # sum/count over LV positions
    MULTI_HOP = "multi_hop"  # answer spans several places
    CONSTRAINT_SURFACING = (
        "constraint_surfacing"  # find the applicable constraint/clause
    )
    CROSS_DOC_CONDITIONAL = (
        "cross_doc_conditional"  # condition in one doc, value in another
    )


class RagQuestionCategory(StrEnum):
    """Which role would ask the question."""

    KALKULATOR = "kalkulator"
    BAULEITER = "bauleiter"


class EvalRunKind(StrEnum):
    """Which grader an eval run executes. rag_* are reserved for the RAG evals (Phase
    6)."""

    CALCULATOR_GOLD = (
        "calculator_gold"  # re-run + grade extraction vs calculation_ground_truth
    )
    CHAT_VALUES = "chat_values"  # replay EKT_CHAT_VALUES over authored fixtures
    RAG_RETRIEVAL = "rag_retrieval"  # retrieval metrics vs rag_ground_truth refs
    RAG_ANSWERS = "rag_answers"  # answer correctness/faithfulness vs rag_ground_truth


class EvalRunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class RenderStyle(StrEnum):
    """displacy render styles served by /nlp/render."""

    DEP = "dep"  # dependency parse, SVG, cached
    ENT = "ent"  # entity highlighting, HTML, uncached


class BlockType(StrEnum):
    """Classification of a reflowed document block (document-reflow spec).

    FURNITURE (letterheads, page numbers) is excluded from reflowed text and is never
    accepted in an analysis include-list; the others are content types selectable per
    analysis request.
    """

    PROSE = "prose"
    HEADING = "heading"
    LIST_ITEM = "list_item"
    TABLE = "table"
    CAPTION = "caption"
    FOOTNOTE = "footnote"
    FURNITURE = "furniture"


class NerFlagKind(StrEnum):
    """The shape of an observed NER misprediction being flagged."""

    WRONG_LABEL = "wrong_label"  # extracted entity carries the wrong label
    NOT_AN_ENTITY = "not_an_entity"  # extracted span should not be an entity
    MISSED_ENTITY = "missed_entity"  # a span that should have been extracted was not


class NerFailureCategory(StrEnum):
    """Closed taxonomy of why an NER misprediction happened, assigned by the LLM error
    analysis and overridable by the user. The dashboard aggregates on this."""

    REGISTER_MISMATCH = (
        "register_mismatch"  # news-trained model vs telegram/technical register
    )
    MISSING_RULE = "missing_rule"  # no entity rule covers the vocabulary
    RULE_ERROR = "rule_error"  # an existing rule fired wrongly or too broadly
    TOKENIZATION = "tokenization"  # tokenizer artifact
    MODEL_LIMITATION = "model_limitation"  # statistical NER wrong guess
    AMBIGUITY = "ambiguity"  # genuinely ambiguous even for a domain expert
    OTHER = "other"


class NerFlagStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"


class ProjectInfoQuery(StrEnum):
    """Keys of the versioned RAG queries that fill the project header fields. Each key
    maps to one fixed `projects` column (see `shared.models.rag_query`)."""

    PROJECT_DESCRIPTION = "project-description"
    PROJECT_MASSNAHMENUMMER = "project-massnahmenummer"
    PROJECT_NAME = "project-name"
    PROJECT_VERGABENUMMER = "project-vergabenummer"
    PROJECT_BAULEISTUNG = "project-bauleistung"
    PROJECT_LOCATION = "project-location"
    PROJECT_VERGABESTELLE = "project-vergabestelle"
