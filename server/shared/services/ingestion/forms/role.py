# ruff: noqa: E501 -- the role table keeps one Formblatt per line.
"""Formblatt role from its id.

Who fills a form is a property of the Formblatt, not of the PDF: the same number means
different things in different families, so the role is looked up per `(family, number)`.
The number comes from the printed footer (`forms/identify.py`) first and from a token
in the filename second; the footer wins over a conflicting token because the issuing
authority printed it. Without a known id a Bieter title keyword decides, and otherwise
the role is UNBEKANNT (which is ingested, not skipped). A bare numeric prefix
(`101-Aufforderung ...`) is the tender's own document ordering and is deliberately not a
token.

`FORMBLAETTER` is the role table. Every row was observed in the training corpus.
"""

from __future__ import annotations

import re
import unicodedata
from enum import StrEnum
from pathlib import PurePosixPath
from typing import NamedTuple

from shared.models.enums import FormRole

V = FormRole.VERGABESTELLE
B = FormRole.BIETER


class FormFamily(StrEnum):
    WSV = "wsv"
    HVA_B_STB = "hva_b_stb"
    VHB = "vhb"
    EFB = "efb"


class FormblattSpec(NamedTuple):
    family: FormFamily
    number: str
    title: str
    role: FormRole


EFB_PREIS = "Preis"

# fmt: off
FORMBLAETTER: tuple[FormblattSpec, ...] = (
    FormblattSpec(FormFamily.WSV, "312-B", "Aufforderung zur Abgabe eines Angebots", V),
    FormblattSpec(FormFamily.WSV, "313-B", "Gewichtung der Zuschlagskriterien", V),
    FormblattSpec(FormFamily.WSV, "317-B", "Verzeichnis der vorzulegenden Unterlagen", V),
    FormblattSpec(FormFamily.WSV, "322-B", "Teilnahmebedingungen", V),
    FormblattSpec(FormFamily.WSV, "331-B", "Angebotsschreiben", B),
    FormblattSpec(FormFamily.WSV, "333a-B", "Eigenerklärung zur Eignung", B),
    FormblattSpec(FormFamily.WSV, "341-B", "Leistungsbeschreibung Titelblatt", V),
    FormblattSpec(FormFamily.WSV, "351-B", "Zusätzliche Vertragsbedingungen", V),
    FormblattSpec(FormFamily.WSV, "352-B", "Besondere Vertragsbedingungen", V),
    FormblattSpec(FormFamily.WSV, "392-B", "Verzeichnis der Leistungen anderer Unternehmer", B),
    FormblattSpec(FormFamily.WSV, "393-B", "Verpflichtungserklärung anderer Unternehmer", B),
    FormblattSpec(FormFamily.HVA_B_STB, "101", "Teilnahmebedingungen National", V),
    FormblattSpec(FormFamily.HVA_B_STB, "102", "Teilnahmebedingungen EU", V),
    FormblattSpec(FormFamily.HVA_B_STB, "103", "Unterauftragnehmer-/Nachunternehmerleistungen", B),
    FormblattSpec(FormFamily.HVA_B_STB, "104", "Eignungsleihe wirtschaftliche und finanzielle Leistungsfähigkeit", B),
    FormblattSpec(FormFamily.HVA_B_STB, "105", "Verpflichtungserklärung", B),
    FormblattSpec(FormFamily.HVA_B_STB, "106", "Erklärung Bietergemeinschaft", B),
    FormblattSpec(FormFamily.HVA_B_STB, "107", "Eigenerklärung Eignung", B),
    FormblattSpec(FormFamily.HVA_B_STB, "108", "Information Datenschutz", V),
    FormblattSpec(FormFamily.HVA_B_STB, "109", "Vorzulegende Unterlagen", V),
    FormblattSpec(FormFamily.HVA_B_STB, "111", "Aufforderung zur Angebotsabgabe", V),
    FormblattSpec(FormFamily.HVA_B_STB, "112", "EU Aufforderung zur Angebotsabgabe", V),
    FormblattSpec(FormFamily.HVA_B_STB, "121", "Angebotsschreiben", B),
    FormblattSpec(FormFamily.HVA_B_STB, "131", "Besondere Vertragsbedingungen", V),
    FormblattSpec(FormFamily.HVA_B_STB, "132", "Weitere Besondere Vertragsbedingungen", V),
    FormblattSpec(FormFamily.HVA_B_STB, "144", "Titelblatt Leistungsbeschreibung", V),
    FormblattSpec(FormFamily.HVA_B_STB, "152", "Bewerbungsbedingungen Teilnahmewettbewerb EU", V),
    FormblattSpec(FormFamily.HVA_B_STB, "153", "Erklärung Bewerbergemeinschaft", B),
    FormblattSpec(FormFamily.HVA_B_STB, "155", "Aufforderung Teilnahmewettbewerb EU", V),
    FormblattSpec(FormFamily.HVA_B_STB, "157", "Teilnahmeantrag", B),
    FormblattSpec(FormFamily.HVA_B_STB, "158", "Vorzulegende Unterlagen Teilnahmewettbewerb", V),
    FormblattSpec(FormFamily.VHB, "124", "Eigenerklärung", B),
    FormblattSpec(FormFamily.VHB, "211", "Aufforderung zur Abgabe eines Angebots", V),
    FormblattSpec(FormFamily.VHB, "212", "Teilnahmebedingungen", V),
    FormblattSpec(FormFamily.VHB, "213", "Angebotsschreiben", B),
    FormblattSpec(FormFamily.VHB, "214", "Besondere Vertragsbedingungen", V),
    FormblattSpec(FormFamily.VHB, "216", "Verzeichnis der vorzulegenden Unterlagen", V),
    FormblattSpec(FormFamily.VHB, "221", "Zuschlagskalkulation", B),
    FormblattSpec(FormFamily.VHB, "222", "Kalkulation über die Endsumme", B),
    FormblattSpec(FormFamily.VHB, "233", "Verzeichnis der Nachunternehmerleistungen", B),
    FormblattSpec(FormFamily.VHB, "234", "Erklärung Bieter-/Arbeitsgemeinschaft", B),
    FormblattSpec(FormFamily.VHB, "235", "Verzeichnis der Leistungen und Kapazitäten anderer Unternehmen", B),
    FormblattSpec(FormFamily.VHB, "236", "Verpflichtungserklärung anderer Unternehmen", B),
    FormblattSpec(FormFamily.VHB, "241", "Abfall", B),
    FormblattSpec(FormFamily.VHB, "244", "Datenverarbeitung", B),
    FormblattSpec(FormFamily.VHB, "401", "Erklärung Bieter-/Arbeitsgemeinschaft (WSV-Nummerierung)", B),
    FormblattSpec(FormFamily.VHB, "421", "Erklärung Holzprodukte (WSV-Nummerierung)", B),
    FormblattSpec(FormFamily.EFB, EFB_PREIS, "Preisermittlung", B),
)
# fmt: on

# Token regexes on the basename, tried in this order; group 1 is the number.
_TOKENS: tuple[tuple[FormFamily, re.Pattern[str]], ...] = (
    (FormFamily.WSV, re.compile(r"FB[ _-]?(\d{3}[a-z]?)-B(?![a-z])", re.IGNORECASE)),
    (
        FormFamily.HVA_B_STB,
        re.compile(r"HVA[ _-]?B[ _-]?StB[ _-]?(\d{3})(?!\d)", re.IGNORECASE),
    ),
    (
        FormFamily.VHB,
        re.compile(
            r"(?:VHB|FB|Formblatt)[ _-]?(\d{3})(?![\da-z]?-B(?![a-z]))(?!\d)",
            re.IGNORECASE,
        ),
    ),
    (FormFamily.EFB, re.compile(r"EFB[ _-]*(Preis)", re.IGNORECASE)),
)
WSV_SUFFIX = "-B"

# Substrings of a Bieter form title, in umlaut-free spelling (see `_fold`). Not
# "verzeichnis": both roles use it.
BIETER_KEYWORDS: tuple[str, ...] = (
    "angebotsschreiben",
    "eigenerklaerung",
    "efb",
    "eignungsleihe",
    "verpflichtungserklaerung",
    "bietergemeinschaft",
    "bewerbergemeinschaft",
    "arbeitsgemeinschaft",
    "nachunternehmer",
    "unterauftragnehmer",
    "teilnahmeantrag",
    "nachweis",
)

_UMLAUTS = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})


def _index_by_family(
    rows: tuple[FormblattSpec, ...],
) -> dict[FormFamily, dict[str, FormblattSpec]]:
    index: dict[FormFamily, dict[str, FormblattSpec]] = {f: {} for f in FormFamily}
    for row in rows:
        if row.number in index[row.family]:
            raise ValueError(f"duplicate Formblatt {row.family} {row.number}")
        index[row.family][row.number] = row
    return index


_ROLE_BY_FAMILY = _index_by_family(FORMBLAETTER)


def format_form_id(family: FormFamily, number: str) -> str:
    """The display id of a Formblatt: `FB 312-B`, `HVA B-StB 121`, `VHB 221`,
    `EFB-Preis`."""
    match family:
        case FormFamily.WSV:
            return f"FB {number}"
        case FormFamily.HVA_B_STB:
            return f"HVA B-StB {number}"
        case FormFamily.VHB:
            return f"VHB {number}"
        case FormFamily.EFB:
            return f"EFB-{number}"


def lookup_formblatt(family: FormFamily, number: str) -> FormblattSpec | None:
    return _ROLE_BY_FAMILY[family].get(number)


def classify_form_role(
    file_name: str, content_id: tuple[FormFamily, str] | None = None
) -> tuple[FormRole, str | None]:
    """(role, form_id) of a form from its printed id, then its filename token, then a
    Bieter title keyword. form_id is rendered from the first id present and is None
    when the form has neither."""
    name = unicodedata.normalize("NFC", PurePosixPath(file_name).name)
    ids = [i for i in (content_id, _find_token(name)) if i is not None]
    form_id = format_form_id(*ids[0]) if ids else None
    for family, number in ids:
        spec = lookup_formblatt(family, number)
        if spec is not None:
            return spec.role, form_id
    folded = _fold(name)
    if any(keyword in folded for keyword in BIETER_KEYWORDS):
        return FormRole.BIETER, form_id
    return FormRole.UNBEKANNT, form_id


def _find_token(name: str) -> tuple[FormFamily, str] | None:
    for family, pattern in _TOKENS:
        match = pattern.search(name)
        if match is None:
            continue
        number = match.group(1)
        if family is FormFamily.WSV:
            return family, f"{number.lower()}{WSV_SUFFIX}"
        if family is FormFamily.EFB:
            return family, EFB_PREIS
        return family, number
    return None


def _fold(name: str) -> str:
    """Lowercase with umlauts spelled out, so `Eigenerklärung` and `Eigenerklaerung`
    match the same keyword."""
    return name.lower().translate(_UMLAUTS)
