from __future__ import annotations

import pytest

from shared.models.enums import FormRole
from shared.services.ingestion.forms.role import (
    FORMBLAETTER,
    FormblattSpec,
    FormFamily,
    _index_by_family,
    classify_form_role,
    format_form_id,
)

# A filename shape observed in the corpus per family.
FILE_NAME_BY_FAMILY = {
    FormFamily.WSV: "T1.1 FB {number} Formblatt.pdf",
    FormFamily.HVA_B_STB: "HVA_B_StB_{number}_Vorlage.pdf",
    FormFamily.VHB: "VHB_{number}_Formblatt.pdf",
    FormFamily.EFB: "EFB-Preis 1 und 2.pdf",
}


@pytest.mark.parametrize("spec", FORMBLAETTER, ids=lambda s: f"{s.family}-{s.number}")
def test_every_table_row_resolves(spec: FormblattSpec) -> None:
    file_name = FILE_NAME_BY_FAMILY[spec.family].format(number=spec.number)
    assert classify_form_role(file_name) == (
        spec.role,
        format_form_id(spec.family, spec.number),
    )


@pytest.mark.parametrize(
    ("file_name", "expected"),
    [
        ("T1.1 FB 312-B Aufforderung Angebot.pdf", (FormRole.VERGABESTELLE, "FB 312-B")),
        ("T1.7 FB 333a-B Eigenerklärung zur Eignung.pdf", (FormRole.BIETER, "FB 333a-B")),
        ("T1.17 FB 401 Erklärung Bieter.pdf", (FormRole.BIETER, "VHB 401")),
        ("HVA_B_StB_104_2_Vorlage_Eignungsleihe.pdf", (FormRole.BIETER, "HVA B-StB 104")),
        ("HVA_B_StB_121_Vorlage_Angebotsschreiben_EV.pdf", (FormRole.BIETER, "HVA B-StB 121")),
        ("FB 211, 212, 214, 213, 233.pdf", (FormRole.VERGABESTELLE, "VHB 211")),
        ("EFB - Preis 1 und 2_22-05-2026.pdf", (FormRole.BIETER, "EFB-Preis")),
        ("Heftung/VHB_244-Datenverarbeitung_Straßenbau.pdf", (FormRole.BIETER, "VHB 244")),
    ],
)
def test_corpus_file_names(file_name: str, expected: tuple[FormRole, str]) -> None:
    assert classify_form_role(file_name) == expected


def test_family_decides_the_number() -> None:
    # HVA B-StB 103 is a Bieter form; a bare "103-" prefix is tender ordering only.
    assert classify_form_role("HVA_B_StB_103_Nachunternehmer.pdf")[0] is FormRole.BIETER
    assert classify_form_role("103-Vorzulegende Unterlagen.pdf") == (
        FormRole.UNBEKANNT,
        None,
    )


def test_unknown_number_in_known_family_keeps_form_id() -> None:
    assert classify_form_role("HVA_B_StB_199_Sonstiges.pdf") == (
        FormRole.UNBEKANNT,
        "HVA B-StB 199",
    )


@pytest.mark.parametrize(
    "file_name",
    [
        "Eigenerklärung Bezug zu Russland.pdf",
        "EU_Eigenerklaerung_Art_5k_VO_EU.pdf",
        "Angebotsschreiben - bei Abgabe zu verwenden.pdf",
        "HVA_B_StB_Eignungsleihe_technische_und_berufliche_Leistungsfaehigkeit.pdf",
        "Nachweis für Sicherungsarbeiten an Arbeitsstellen.pdf",
        "Verpflichtungserklärung.pdf",
        "Verpflichtungserklaerung.pdf",
    ],
)
def test_bieter_keyword_fallback(file_name: str) -> None:
    assert classify_form_role(file_name) == (FormRole.BIETER, None)


def test_decomposed_umlauts_match_keywords() -> None:
    decomposed = "Eigenerklärung.pdf"
    assert classify_form_role(decomposed) == (FormRole.BIETER, None)


@pytest.mark.parametrize(
    "file_name",
    [
        "04 Baustelleninformationsschild.pdf",
        "Informationspflicht zur Nachprüfung nach 14 ThürVgG.pdf",
        "TTSiB Projektdatenblatt FG231.pdf",
    ],
)
def test_expected_unbekannt_forms(file_name: str) -> None:
    assert classify_form_role(file_name) == (FormRole.UNBEKANNT, None)


def test_verzeichnis_is_not_a_keyword() -> None:
    assert classify_form_role("Verzeichnis der Unterlagen.pdf")[0] is FormRole.UNBEKANNT


def test_form_id_rendering() -> None:
    assert format_form_id(FormFamily.WSV, "312-B") == "FB 312-B"
    assert format_form_id(FormFamily.HVA_B_STB, "121") == "HVA B-StB 121"
    assert format_form_id(FormFamily.VHB, "221") == "VHB 221"
    assert format_form_id(FormFamily.EFB, "Preis") == "EFB-Preis"


def test_duplicate_rows_raise() -> None:
    row = FormblattSpec(FormFamily.VHB, "211", "x", FormRole.VERGABESTELLE)
    with pytest.raises(ValueError, match="duplicate"):
        _index_by_family((row, row))


def test_dash_word_after_vhb_number_is_not_a_wsv_suffix() -> None:
    assert classify_form_role("VHB_213-Bieterangebot.pdf") == (
        FormRole.BIETER,
        "VHB 213",
    )
