"""GAEB 90 record layout: Zeilenarten, fixed column slices, and the OZ mask.

A GAEB 90 file is a sequence of 80-column records: columns 1-2 hold the Zeilenart,
columns 75-80 the running Satznummer, and the columns between carry fixed-position
fields per Zeilenart. The OZMASKE from the Eroeffnungssatz (e.g. '1122PPPPI') describes
how the 9-character OZ field splits into hierarchy segments plus an optional
alphanumeric index; `OzMask` formats raw OZ fields into the dotted form used across the
LV models (e.g. '01.02.0030').
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from shared.models.llm_output_schemas.lv_extraction import (
    POSITIONSTYP_ALTERNATIV,
    POSITIONSTYP_BEDARF,
    POSITIONSTYP_GRUND,
    POSITIONSTYP_NORMAL,
)
from shared.services.ingestion.gaeb.compose import OZ_SEGMENT_SEP, GaebParseError

RECORD_LENGTH = 80

# Zeilenarten (record types), columns 1-2. T0/T1/T9 frame the vertraglichen Regelungen,
# GAEB 90's slot for LV-level Vorbemerkungen; the block precedes the Eroeffnungssatz.
ZA_VERTRAGLICHE_REGELUNG_BEGIN = "T0"
ZA_VERTRAGLICHE_REGELUNG_TEXT = "T1"
ZA_VERTRAGLICHE_REGELUNG_END = "T9"
ZA_EROEFFNUNG = "00"
ZA_LOS_BEGIN = "10"
ZA_GRUPPE_BEGIN = "11"
ZA_GRUPPE_BEZEICHNUNG = "12"
ZA_HINWEIS_BEGIN = "20"
ZA_POSITION_BEGIN = "21"
ZA_UNTERBESCHREIBUNG = "24"
ZA_KURZTEXT = "25"
ZA_LANGTEXT = "26"
ZA_LB_ZUORDNUNG = "27"
ZA_EINHEITSPREIS = "22"
ZA_PREISE = "23"
ZA_EP_ANTEILE = "30"
ZA_GRUPPE_END = "31"

# Price/statistics records that sit inside a Teilleistung element, between its begin
# record (21) and its text records (25/26); they must not disturb the text sink.
ZA_POSITION_DATA = (ZA_EINHEITSPREIS, ZA_PREISE, ZA_LB_ZUORDNUNG, ZA_EP_ANTEILE)
ZA_LOS_END = "33"
ZA_ABSCHLUSS = "99"

# Header records 01-08 carry LV/project metadata we do not emit.
ZA_HEADER_INFO = ("01", "02", "03", "04", "05", "06", "07", "08")

# Content region between the Zeilenart and the Satznummer (columns 75-80).
SLICE_CONTENT = slice(2, 74)

# Eroeffnungssatz (00): exchange phase, OZ mask, GAEB-Regelung year.
SLICE_AUSTAUSCHPHASE = slice(10, 12)
SLICE_OZMASKE = slice(62, 71)
AUSTAUSCHPHASE_D83 = "83"

# Positions- (21), Gruppen- (11) and Hinweis- (20) records: the 9-character OZ field.
SLICE_OZ = slice(2, 11)

# Position (21) fields.
SLICE_POSART_1 = slice(11, 12)
SLICE_POSART_2 = slice(12, 13)
SLICE_MENGE = slice(23, 34)
SLICE_EINHEIT = slice(34, 38)
SLICE_STL_NR = slice(43, 60)
MENGE_INTEGER_DIGITS = (
    8  # Menge is 11 digits stored without a separator: 8 integer + 3 decimal
)

POSART_NORMAL = "N"
POSART_GRUND = "G"
POSART_ALTERNATIV = "A"
POSART_BEDARF_OHNE_GB = "E"
POSART_BEDARF_MIT_GB = "M"

OZ_MASK_INDEX_CHAR = "I"


class D83ParseError(GaebParseError):
    """The file violates the GAEB 90 D83 record structure."""


def positionstyp_from_posart(posart1: str, posart2: str) -> str:
    """Map the ZA 21 Positionsart fields onto the shared Positionstyp vocabulary."""
    if posart2 in (POSART_BEDARF_OHNE_GB, POSART_BEDARF_MIT_GB):
        return POSITIONSTYP_BEDARF
    if posart1 == POSART_GRUND:
        return POSITIONSTYP_GRUND
    if posart1 == POSART_ALTERNATIV:
        return POSITIONSTYP_ALTERNATIV
    return POSITIONSTYP_NORMAL


@dataclass(frozen=True)
class OzMask:
    """The OZ structure from the Eroeffnungssatz: hierarchy segment lengths plus index
    length."""

    segment_lengths: tuple[int, ...]
    index_length: int

    @classmethod
    def from_mask(cls, mask: str) -> OzMask:
        """Parse an OZMASKE like '1122PPPPI' into run lengths; the trailing 'I' run is
        the index."""
        mask = mask.strip()
        if not mask:
            raise D83ParseError("Eroeffnungssatz carries no OZMASKE")
        runs: list[tuple[str, int]] = []
        for char in mask:
            if runs and runs[-1][0] == char:
                runs[-1] = (char, runs[-1][1] + 1)
            else:
                runs.append((char, 1))
        index_length = 0
        if runs[-1][0] == OZ_MASK_INDEX_CHAR:
            index_length = runs[-1][1]
            runs = runs[:-1]
        if not runs:
            raise D83ParseError(f"OZMASKE {mask!r} has no hierarchy segments")
        return cls(
            segment_lengths=tuple(length for _, length in runs),
            index_length=index_length,
        )

    def split(self, raw_oz: str) -> list[str]:
        """Split a raw OZ field into its filled segments (the index, when present, is
        last). Segments are zero-filled to their mask width; a blank segment followed
        by a filled one (a position placed directly under a higher-level LV-Gruppe, or
        a space-padded number) is skipped rather than rejected, since real exports do
        both."""
        segments: list[str] = []
        position = 0
        for length in self.segment_lengths:
            segment = raw_oz[position : position + length].strip()
            position += length
            if not segment:
                continue
            if not segment.isdigit():
                raise D83ParseError(
                    f"OZ segment {segment!r} in {raw_oz!r} is not numeric"
                )
            segments.append(segment.zfill(length))
        index = raw_oz[position : position + self.index_length].strip()
        if index:
            segments.append(index)
        return segments

    def format(self, raw_oz: str) -> str:
        """Dotted OZ as the LV models use it, e.g. '01.02.0030' or '10.14.0010.a'."""
        segments = self.split(raw_oz)
        if not segments:
            raise D83ParseError(f"OZ field {raw_oz!r} is empty")
        return OZ_SEGMENT_SEP.join(segments)


def parse_menge(field: str) -> Decimal | None:
    """The Menge field: 11 digits without separator (8 integer + 3 decimal); blank when
    unset."""
    if not field.strip():
        return None
    try:
        return Decimal(f"{field[:MENGE_INTEGER_DIGITS]}.{field[MENGE_INTEGER_DIGITS:]}")
    except InvalidOperation as exc:
        raise D83ParseError(f"Menge field {field!r} is not numeric") from exc
