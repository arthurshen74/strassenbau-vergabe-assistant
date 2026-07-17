"""GAEB 90 D83 reader: decode CP850 and walk the 80-column records into LV items.

The reader is a small state machine over the Zeilenarten: `11`/`12` open an LV-Gruppe
and name it (emitted as a Titel item), `21` starts a Teilleistung whose `25`/`26`
records carry the Kurz-/Langtext, `20` starts a Hinweistext whose `26` records govern
every following priced position until the enclosing LV-Gruppe closes (`31`); a
Hinweistext that precedes a top-level LV-Gruppe is absorbed by that group, so it governs
only that Abschnitt and not the rest of the file. `T1` records before the
Eroeffnungssatz are a file-level Vorbemerkung that applies to every position. Price- and
statistics-records (`23`, `27`, ...) carry nothing the LV emission needs and are
skipped.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum, auto

from shared.services.ingestion.gaeb.compose import RawLVItem, compose
from shared.services.ingestion.gaeb.d83 import records as rec
from shared.services.ingestion.gaeb.d83.records import D83ParseError
from shared.services.ingestion.lv.types import LVParseResult

GAEB_D83_SUFFIX = ".d83"
ENCODING = "cp850"

HINWEIS_BLOCK_SEP = "\n\n"
KURZTEXT_JOIN = " "

# Bietertextergänzung furniture, blanked in place so column alignment (and thus the
# dedenting) is preserved: a Langtext record may start with its two-digit
# Ergänzungszeilen number plus the kind letter 'A' in the margin columns, and '...
# Freitext ...' prints a bidder fill-in field. Neither is contract text.
TEXTERGAENZUNG_PREFIX_RE = re.compile(r"^\d{2}A")
TEXTERGAENZUNG_PREFIX_BLANK = "   "
FREITEXT_MARKER = "... Freitext ..."
FREITEXT_BLANK = " " * len(FREITEXT_MARKER)


def is_d83_file(file_name: str) -> bool:
    return file_name.lower().endswith(GAEB_D83_SUFFIX)


def parse_d83(data: bytes) -> LVParseResult:
    """Parse D83 bytes into the LVParseResult shape shared with the LV ingestion
    path."""
    reader = _Reader()
    for line in data.decode(ENCODING).splitlines():
        if line.strip():
            reader.read(line.ljust(rec.RECORD_LENGTH))
    return compose(*reader.finish())


class _Sink(StrEnum):
    """Where the current text records (12/25/26) belong."""

    NONE = auto()
    GROUP_TITLE = auto()
    HINWEIS = auto()
    POSITION = auto()
    VORBEMERKUNG = auto()
    SKIP = auto()


@dataclass
class _ItemBuilder:
    """A Titel or Teilleistung while its text records are still being collected."""

    oz: str
    is_title: bool
    posart1: str = ""
    posart2: str = ""
    menge: Decimal | None = None
    einheit: str = ""
    stl_nr: str | None = None
    kurztext_lines: list[str] = field(default_factory=list)
    langtext_lines: list[str] = field(default_factory=list)
    hinweis_blocks: list[str] = field(default_factory=list)

    def finish(self) -> RawLVItem:
        return RawLVItem(
            oz=self.oz,
            is_title=self.is_title,
            kurztext=KURZTEXT_JOIN.join(
                line.strip() for line in self.kurztext_lines if line.strip()
            ),
            langtext=_dedent(self.langtext_lines),
            hinweis=HINWEIS_BLOCK_SEP.join(self.hinweis_blocks) or None,
            menge=self.menge,
            einheit=self.einheit,
            stl_nr=self.stl_nr,
            positionstyp=(
                None
                if self.is_title
                else rec.positionstyp_from_posart(self.posart1, self.posart2)
            ),
        )


@dataclass
class _Group:
    """An open LV-Gruppe: its Titel item plus the Hinweis blocks collected inside it."""

    builder: _ItemBuilder
    hinweis_blocks: list[str] = field(default_factory=list)


class _Reader:
    def __init__(self) -> None:
        self._mask: rec.OzMask | None = None
        self._items: list[_ItemBuilder] = []
        self._warnings: list[str] = []
        self._file_vorbemerkung_blocks: list[str] = []
        self._pending_hinweis_blocks: list[str] = []
        self._groups: list[_Group] = []
        self._sink = _Sink.NONE
        self._position: _ItemBuilder | None = None
        self._block_lines: list[str] = []
        self._finished = False

    def read(self, line: str) -> None:
        za = line[:2]
        content = line[rec.SLICE_CONTENT]
        if za == rec.ZA_LANGTEXT:
            content = TEXTERGAENZUNG_PREFIX_RE.sub(TEXTERGAENZUNG_PREFIX_BLANK, content)
        if za in (rec.ZA_KURZTEXT, rec.ZA_LANGTEXT):
            content = content.replace(FREITEXT_MARKER, FREITEXT_BLANK)
        content = content.rstrip()
        if self._finished:
            self._warnings.append(f"record {za} after Abschlusssatz ignored")
            return
        if za == rec.ZA_VORBEMERKUNG_TEXT:
            self._set_sink(_Sink.VORBEMERKUNG)
            self._block_lines.append(content)
            return
        if za == rec.ZA_KURZTEXT:
            self._read_kurztext(content)
            return
        if za == rec.ZA_LANGTEXT:
            self._read_langtext(content)
            return
        if za == rec.ZA_GRUPPE_BEZEICHNUNG:
            self._read_gruppe_bezeichnung(content)
            return
        if za in rec.ZA_POSITION_DATA:
            return

        # Every other Zeilenart terminates the open text block.
        if za == rec.ZA_EROEFFNUNG:
            self._set_sink(_Sink.NONE)
            self._read_eroeffnung(line)
        elif za == rec.ZA_GRUPPE_BEGIN:
            self._set_sink(_Sink.GROUP_TITLE)
            self._open_gruppe(line)
            self._absorb_pending_hinweis()
        elif za == rec.ZA_HINWEIS_BEGIN:
            self._set_sink(_Sink.HINWEIS)
        elif za == rec.ZA_POSITION_BEGIN:
            self._set_sink(_Sink.POSITION)
            self._open_position(line)
        elif za == rec.ZA_UNTERBESCHREIBUNG:
            self._set_sink(_Sink.SKIP)
            self._warnings.append("Unterbeschreibung (ZA 24) skipped")
        elif za == rec.ZA_GRUPPE_END:
            self._set_sink(_Sink.NONE)
            self._close_gruppe()
        elif za == rec.ZA_ABSCHLUSS:
            self._set_sink(_Sink.NONE)
            if self._groups:
                raise D83ParseError("Abschlusssatz (ZA 99) with unclosed LV-Gruppen")
            self._finished = True
        elif za in (rec.ZA_LOS_BEGIN, rec.ZA_LOS_END):
            self._set_sink(_Sink.NONE)
            self._warnings.append(f"Los record (ZA {za}) ignored")
        elif za in rec.ZA_HEADER_INFO or za in (
            rec.ZA_VORBEMERKUNG_BEGIN,
            rec.ZA_VORBEMERKUNG_END,
        ):
            self._set_sink(_Sink.NONE)
        else:
            self._set_sink(_Sink.NONE)
            self._warnings.append(f"unsupported record type {za!r} ignored")

    def finish(self) -> tuple[list[RawLVItem], list[str]]:
        self._set_sink(_Sink.NONE)
        if self._groups:
            raise D83ParseError("file ended with unclosed LV-Gruppen")
        if not self._finished:
            self._warnings.append("file ended without Abschlusssatz (ZA 99)")
        return [builder.finish() for builder in self._items], self._warnings

    def _set_sink(self, sink: _Sink) -> None:
        """Switch the text sink, filing a completed Hinweis/Vorbemerkung block into
        scope."""
        if self._sink in (_Sink.HINWEIS, _Sink.VORBEMERKUNG) and self._block_lines:
            block = _dedent(self._block_lines)
            if block:
                self._store_block(block)
        self._block_lines = []
        self._sink = sink

    def _store_block(self, block: str) -> None:
        """File a finished text block into its governing scope: the open LV-Gruppe if
        any, else a file-level Vorbemerkung (T1) that governs every position, else a
        Hinweis held until the next top-level LV-Gruppe it introduces absorbs it."""
        if self._groups:
            self._groups[-1].hinweis_blocks.append(block)
        elif self._sink is _Sink.VORBEMERKUNG:
            self._file_vorbemerkung_blocks.append(block)
        else:
            self._pending_hinweis_blocks.append(block)

    def _read_eroeffnung(self, line: str) -> None:
        if self._mask is not None:
            self._warnings.append("second Eroeffnungssatz (ZA 00) ignored")
            return
        phase = line[rec.SLICE_AUSTAUSCHPHASE]
        if phase != rec.AUSTAUSCHPHASE_D83:
            self._warnings.append(f"Austauschphase {phase!r} parsed as 83")
        self._mask = rec.OzMask.from_mask(line[rec.SLICE_OZMASKE])

    def _open_gruppe(self, line: str) -> None:
        builder = _ItemBuilder(oz=self._format_oz(line), is_title=True)
        self._items.append(builder)
        self._groups.append(_Group(builder=builder))

    def _absorb_pending_hinweis(self) -> None:
        """Hand a Hinweis that preceded this LV-Gruppe to the group, so it governs only
        this Abschnitt and pops at its Abschluss (ZA 31) instead of every later
        Abschnitt."""
        if self._pending_hinweis_blocks:
            self._groups[-1].hinweis_blocks = self._pending_hinweis_blocks
            self._pending_hinweis_blocks = []

    def _open_position(self, line: str) -> None:
        builder = _ItemBuilder(
            oz=self._format_oz(line),
            is_title=False,
            posart1=line[rec.SLICE_POSART_1].strip(),
            posart2=line[rec.SLICE_POSART_2].strip(),
            menge=rec.parse_menge(line[rec.SLICE_MENGE]),
            einheit=line[rec.SLICE_EINHEIT].strip(),
            stl_nr=line[rec.SLICE_STL_NR].strip() or None,
            hinweis_blocks=self._governing_hinweis_blocks(),
        )
        self._items.append(builder)
        self._position = builder

    def _governing_hinweis_blocks(self) -> list[str]:
        """The Hinweis blocks in scope, outermost first: file-level Vorbemerkungen, a
        Hinweis still waiting for its LV-Gruppe (it governs root positions before any
        group), then each open group."""
        blocks = list(self._file_vorbemerkung_blocks)
        blocks.extend(self._pending_hinweis_blocks)
        for group in self._groups:
            blocks.extend(group.hinweis_blocks)
        return blocks

    def _close_gruppe(self) -> None:
        if not self._groups:
            raise D83ParseError("LV-Gruppen end (ZA 31) without an open group")
        self._groups.pop()
        self._position = None

    def _read_kurztext(self, content: str) -> None:
        if self._sink is _Sink.POSITION and self._position is not None:
            self._position.kurztext_lines.append(content)
        elif self._sink is not _Sink.SKIP:
            self._warnings.append("Kurztext record (ZA 25) outside a position ignored")

    def _read_langtext(self, content: str) -> None:
        if self._sink is _Sink.POSITION and self._position is not None:
            self._position.langtext_lines.append(content)
        elif self._sink in (_Sink.HINWEIS, _Sink.VORBEMERKUNG):
            self._block_lines.append(content)
        elif self._sink is _Sink.GROUP_TITLE:
            self._groups[-1].builder.langtext_lines.append(content)
        elif self._sink is not _Sink.SKIP:
            self._warnings.append("Langtext record (ZA 26) without a target ignored")

    def _read_gruppe_bezeichnung(self, content: str) -> None:
        if self._sink is _Sink.GROUP_TITLE and self._groups:
            self._groups[-1].builder.kurztext_lines.append(content)
        else:
            self._warnings.append(
                "LV-Gruppe name (ZA 12) outside a group header ignored"
            )

    def _format_oz(self, line: str) -> str:
        if self._mask is None:
            raise D83ParseError("OZ record before the Eroeffnungssatz (ZA 00)")
        return self._mask.format(line[rec.SLICE_OZ])


def _dedent(lines: list[str]) -> str:
    """Join text record lines, removing the common leading margin (typically three
    spaces)."""
    filled = [line for line in lines if line.strip()]
    if not filled:
        return ""
    margin = min(len(line) - len(line.lstrip(" ")) for line in filled)
    return "\n".join(line[margin:] if line.strip() else "" for line in lines).strip(
        "\n"
    )
