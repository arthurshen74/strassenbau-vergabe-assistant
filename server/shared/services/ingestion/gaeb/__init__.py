"""GAEB Leistungsverzeichnis parsers.

Both exchange formats of the 83 phase (Angebotsaufforderung) parse into the same
`LVParseResult` shape: the fixed-format GAEB 90 `*.d83` and the GAEB DA XML `*.x83`. A
GAEB file is the project's LV by definition; `is_gaeb_lv_file` is the single
classification predicate, and `parse_gaeb_lv` dispatches to the right reader.
"""

from shared.services.ingestion.gaeb.compose import GaebParseError
from shared.services.ingestion.gaeb.d83.parse import (
    GAEB_D83_SUFFIX,
    is_d83_file,
    parse_d83,
)
from shared.services.ingestion.gaeb.d83.records import D83ParseError
from shared.services.ingestion.gaeb.x83.parse import (
    GAEB_X83_SUFFIX,
    X83ParseError,
    is_x83_file,
    parse_x83,
)
from shared.services.ingestion.lv.types import LVParseResult

__all__ = [
    "GAEB_D83_SUFFIX",
    "GAEB_X83_SUFFIX",
    "D83ParseError",
    "GaebParseError",
    "X83ParseError",
    "is_d83_file",
    "is_gaeb_lv_file",
    "is_x83_file",
    "parse_d83",
    "parse_gaeb_lv",
    "parse_x83",
]


def is_gaeb_lv_file(file_name: str) -> bool:
    """True for a GAEB exchange file carrying the project's Leistungsverzeichnis."""
    return is_d83_file(file_name) or is_x83_file(file_name)


def parse_gaeb_lv(file_name: str, data: bytes) -> LVParseResult:
    """Parse a GAEB LV file with the reader matching its format."""
    if is_d83_file(file_name):
        return parse_d83(data)
    if is_x83_file(file_name):
        return parse_x83(data)
    raise GaebParseError(f"{file_name!r} is not a GAEB LV file")
