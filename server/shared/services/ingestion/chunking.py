"""Simple chunking: text units to SimpleChunk drafts (no embeddings).

Every prose document is chunked into `DOCUMENT` chunks from its SourceLine text, and a
form into `FORM` chunks, one or more per form section, carrying only what is checked
(unchecked options and their nested lines stay in `source_lines`); LV items are chunked
into `LV_ITEM` chunks from their resolved long text, and the LV's
Vorbemerkungen/Hinweise into `LV_TEXT` chunks (INGESTION.md).
This module is pure: it produces `ChunkDraft`s carrying everything a `NewSimpleChunk`
needs except the embedding, which the service fills after calling the embeddings client.
"""

from __future__ import annotations

from uuid import UUID

from langchain_text_splitters import RecursiveCharacterTextSplitter
from pydantic import BaseModel, ConfigDict, Field

from shared.models.enums import SourceDocType
from shared.models.lv_item import LVItem
from shared.models.lv_text import LVText
from shared.models.source_line import SourceLine
from shared.services.ingestion.forms.model import (
    FORM_SECTION_PREFIX,
    NO_OPTION_CHECKED,
    OPTION_UNCHECKED_PREFIX,
    is_option_line,
    option_label,
)
from shared.services.ingestion.lv.types import hinweis_text

# Which underlying field a chunk's text was drawn from (denormalised onto every chunk).
SOURCE_DOC_FIELD_DOCUMENT = "sourcelines.line_text"
SOURCE_DOC_FIELD_LV_ITEM = "lv_items.langtext_resolved"
SOURCE_DOC_FIELD_LV_TEXT = "lv_texts.body"

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150
SEPARATORS = ["\n\n", "\n", ". ", " ", ""]

_SPLITTER = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
    separators=SEPARATORS,
)


class ChunkDraft(BaseModel):
    """A SimpleChunk minus the embedding; the service adds embedding +
    embedding_model."""

    model_config = ConfigDict(extra="forbid")

    source_doc_uuid: UUID
    source_doc_type: SourceDocType
    source_doc_field: str
    source_doc_pages: list[int] = Field(default_factory=list)
    chunk_index: int
    oz: str | None = None
    stl_nr: str | None = None
    project_uuid: UUID
    chunk_text: str


def chunk_document(
    source_lines: list[SourceLine],
    *,
    project_uuid: UUID,
    document_uuid: UUID,
) -> list[ChunkDraft]:
    """Chunk a document's joined SourceLine text into DOCUMENT chunks, deriving each
    chunk's pages from the SourceLine rows it spans."""
    ordered = sorted(source_lines, key=lambda line: line.line_id)
    joined = "\n".join(line.line_text for line in ordered)
    char_to_page = _char_to_page(ordered)
    texts = _SPLITTER.split_text(joined)
    pages_per_chunk = _pages_for_chunks(texts, joined, char_to_page)
    return [
        ChunkDraft(
            source_doc_uuid=document_uuid,
            source_doc_type=SourceDocType.DOCUMENT,
            source_doc_field=SOURCE_DOC_FIELD_DOCUMENT,
            source_doc_pages=pages,
            chunk_index=index,
            project_uuid=project_uuid,
            chunk_text=text,
        )
        for index, (text, pages) in enumerate(zip(texts, pages_per_chunk))
    ]


def chunk_form(
    source_lines: list[SourceLine],
    *,
    project_uuid: UUID,
    document_uuid: UUID,
) -> list[ChunkDraft]:
    """Chunk a form's SourceLines into FORM chunks: a section heading line starts a new
    chunk, a line is never split, and a chunk that would exceed CHUNK_SIZE is closed
    and continued in a chunk that repeats the heading. No overlap. Only what is checked
    reaches a chunk: an unchecked option is dropped together with everything printed
    under it (see `_collapse_options`), a checked option loses its marker, and a section
    left empty by that gets the single line NO_OPTION_CHECKED. Pages come from the
    emitted content lines, not the heading."""
    groups: list[tuple[SourceLine | None, list[SourceLine]]] = []
    heading: SourceLine | None = None
    content: list[SourceLine] = []
    size = 0
    for line in _collapse_options(sorted(source_lines, key=lambda line: line.line_id)):
        if line.line_text.startswith(FORM_SECTION_PREFIX):
            if content:
                groups.append((heading, content))
            heading, content, size = line, [], len(line.line_text)
            continue
        if content and size + 1 + len(line.line_text) > CHUNK_SIZE:
            groups.append((heading, content))
            content, size = [], len(heading.line_text) if heading else 0
        size += len(line.line_text) + (1 if size else 0)
        content.append(line)
    if content:
        groups.append((heading, content))
    return [
        ChunkDraft(
            source_doc_uuid=document_uuid,
            source_doc_type=SourceDocType.FORM,
            source_doc_field=SOURCE_DOC_FIELD_DOCUMENT,
            source_doc_pages=sorted({line.page for line in lines}),
            chunk_index=index,
            project_uuid=project_uuid,
            chunk_text="\n".join(
                line.line_text for line in ([head, *lines] if head else lines)
            ),
        )
        for index, (head, lines) in enumerate(groups)
    ]


def _collapse_options(ordered: list[SourceLine]) -> list[SourceLine]:
    """Drop every unchecked option and what is nested under it. After an unchecked
    option at x0, lines are dropped until a heading, an option line at x0 or further
    left, or an unmarked line further left than x0 (an unmarked line at x0 is the
    option's own continuation). A line without geometry drops only itself. Checked
    options are emitted as their printed text. A section whose lines were all dropped
    emits NO_OPTION_CHECKED under its heading."""
    result: list[SourceLine] = []
    dropping_below_x0: float | None = None
    heading_index: int | None = None
    section_had_lines = False
    for line in ordered:
        text = line.line_text
        x0 = line.bbox[0]
        if text.startswith(FORM_SECTION_PREFIX):
            if heading_index is not None and section_had_lines:
                _fill_empty_section(result, heading_index, ordered[0].document_uuid)
            result.append(line)
            heading_index = len(result) - 1
            section_had_lines, dropping_below_x0 = False, None
            continue
        section_had_lines = True
        is_option = is_option_line(text)
        if dropping_below_x0 is not None:
            clears = x0 <= dropping_below_x0 if is_option else x0 < dropping_below_x0
            if not clears:
                continue
            dropping_below_x0 = None
        if text.startswith(OPTION_UNCHECKED_PREFIX):
            dropping_below_x0 = x0 if any(line.bbox) else None
            continue
        if is_option:
            line = line.model_copy(update={"line_text": option_label(text)})
        result.append(line)
    if heading_index is not None and section_had_lines:
        _fill_empty_section(result, heading_index, ordered[0].document_uuid)
    return result


def _fill_empty_section(
    result: list[SourceLine], heading_index: int, document_uuid: UUID
) -> None:
    """Append NO_OPTION_CHECKED after the heading at `heading_index` when nothing
    followed it."""
    if heading_index != len(result) - 1:
        return
    heading = result[heading_index]
    result.append(
        heading.model_copy(
            update={"line_text": NO_OPTION_CHECKED, "document_uuid": document_uuid}
        )
    )


def chunk_lv_item(
    item: LVItem,
    pages: list[int],
    *,
    project_uuid: UUID,
) -> list[ChunkDraft]:
    """Chunk one LV item's (langtext_resolved || langtext) into LV_ITEM chunks, carrying
    the item's oz/stl_nr and pages on every chunk."""
    text = item.langtext_resolved or item.langtext
    return [
        ChunkDraft(
            source_doc_uuid=item.lv_item_uuid,
            source_doc_type=SourceDocType.LV_ITEM,
            source_doc_field=SOURCE_DOC_FIELD_LV_ITEM,
            source_doc_pages=pages,
            chunk_index=index,
            oz=item.oz,
            stl_nr=item.stl_nr,
            project_uuid=project_uuid,
            chunk_text=chunk_text,
        )
        for index, chunk_text in enumerate(_SPLITTER.split_text(text))
    ]


def chunk_lv_text(text: LVText, *, project_uuid: UUID) -> list[ChunkDraft]:
    """Chunk one LV text (heading plus body) into LV_TEXT chunks. `oz` carries the
    text's own identifier or, for a Hinweis, its enclosing LV-Gruppe; a Vortext has
    none."""
    content = hinweis_text(text.heading, text.body)
    return [
        ChunkDraft(
            source_doc_uuid=text.lv_text_uuid,
            source_doc_type=SourceDocType.LV_TEXT,
            source_doc_field=SOURCE_DOC_FIELD_LV_TEXT,
            chunk_index=index,
            oz=text.oz or text.parent_oz,
            project_uuid=project_uuid,
            chunk_text=chunk_text,
        )
        for index, chunk_text in enumerate(_SPLITTER.split_text(content))
    ]


def _char_to_page(ordered_lines: list[SourceLine]) -> list[int]:
    """Map each character index of the joined text to the page of its SourceLine."""
    pages: list[int] = []
    for index, line in enumerate(ordered_lines):
        if index > 0:
            pages.append(line.page)  # the "\n" join character sits on this line's page
        pages.extend([line.page] * len(line.line_text))
    return pages


def _pages_for_chunks(
    chunks: list[str], joined: str, char_to_page: list[int]
) -> list[list[int]]:
    """Locate each chunk in the joined text (via an advancing cursor, so overlapping
    chunks resolve) and collect the distinct pages it spans."""
    result: list[list[int]] = []
    cursor = 0
    for chunk in chunks:
        index = joined.find(chunk, cursor)
        if index == -1:
            index = joined.find(chunk)
        if index == -1:
            result.append([])
            continue
        end = min(index + len(chunk), len(char_to_page))
        result.append(sorted({char_to_page[i] for i in range(index, end)}))
        cursor = index + 1
    return result
