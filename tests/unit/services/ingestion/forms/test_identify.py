from __future__ import annotations

import pytest

from shared.services.ingestion.forms.identify import (
    identify_formblatt,
    identify_from_text,
)
from shared.services.ingestion.forms.role import FormFamily
from tests.form_pdfs import Text, flattened_pdf, hva_111_page


@pytest.mark.parametrize(
    ("text", "number"),
    [
        (
            "Seite 3\n111 HVA B-StB Vorlage Aufforderung zur Angebotsabgabe 03-23\n",
            "111",
        ),
        ("101 HVA B-StB Vordruck Teilnahmebedingungen National 03-23", "101"),
        ("104.1 HVA B-StB Eignungsleihe wirtschaftliche Leistungsfähigkeit", "104"),
        (
            "  111 HVA B-StB Vorlage Aufforderung zur Angebotsabgabe NTVergG 02-24",
            "111",
        ),
        (
            "109 HVA-B Vorlage Vorzulegende Unterlagen\n109 HVA B-StB Vorlage 03-26",
            "109",
        ),
    ],
)
def test_hva_footer_resolves(text: str, number: str) -> None:
    assert identify_from_text(text) == (FormFamily.HVA_B_STB, number)


@pytest.mark.parametrize(
    "text",
    [
        "Baubeschreibung\n1.5 Mindestanforderungen an Nebenangebote\n16540 Hohen Neuendorf",
        "Siehe Muster „HVA B-StB Vorzulegende Unterlagen“ (Abschnitt 1)",
        "Vergabenummer 111 HVA Ausschreibung",
        "",
    ],
)
def test_prose_does_not_resolve(text: str) -> None:
    assert identify_from_text(text) is None


def test_footer_is_read_from_the_pdf() -> None:
    assert identify_formblatt(hva_111_page()) == (FormFamily.HVA_B_STB, "111")


def test_pdf_without_footer_and_garbage_yield_none() -> None:
    assert (
        identify_formblatt(flattened_pdf([], [Text(62, 800, "Baubeschreibung")]))
        is None
    )
    assert identify_formblatt(b"not a pdf at all") is None
