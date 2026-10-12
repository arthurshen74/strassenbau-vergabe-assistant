"""Fact templates and the row shape of the facts editor.

The templates are the questions a Kalkulator asks of the Vergabestelle forms; the
labeler fills gold and Fundstelle, deletes what a tender does not have and adds free
rows. A list gold is edited as one string with `; ` between the items.
"""

from __future__ import annotations

from typing import Any

from scripts.form_labeler.store import Fact, FactFile, FactKind, FactSource

LIST_SEPARATOR = "; "

COL_KEY = "key"
COL_QUESTION = "question"
COL_KIND = "kind"
COL_GOLD = "gold"
COL_PDF = "source_pdf"
COL_PAGE = "source_page"
COL_SECTION = "source_section"
COLUMNS = (COL_KEY, COL_QUESTION, COL_KIND, COL_GOLD, COL_PDF, COL_PAGE, COL_SECTION)

# (key, question, kind, usual form)
FACT_TEMPLATES: tuple[tuple[str, str, FactKind, str], ...] = (
    (
        "nebenangebote_zugelassen",
        "Sind Nebenangebote zugelassen?",
        FactKind.YES_NO,
        "111 § 6",
    ),
    ("losweise_vergabe", "Erfolgt die Vergabe losweise?", FactKind.YES_NO, "111 § 4"),
    (
        "mehrere_hauptangebote",
        "Sind mehrere Hauptangebote zugelassen?",
        FactKind.YES_NO,
        "111 § 5",
    ),
    (
        "nachforderung",
        "Werden fehlende Unterlagen nachgefordert?",
        FactKind.YES_NO,
        "111 § 3.3",
    ),
    (
        "kommunikation_elektronisch",
        "Erfolgt die Kommunikation elektronisch über die Vergabeplattform?",
        FactKind.YES_NO,
        "111",
    ),
    (
        "angebotsform",
        "In welcher Form ist das Angebot einzureichen?",
        FactKind.LIST,
        "111",
    ),
    (
        "zuschlagskriterien",
        "Welche Zuschlagskriterien gelten?",
        FactKind.LIST,
        "111 § 7",
    ),
    (
        "zuschlagsfrist",
        "Wann endet die Zuschlags-/Bindefrist?",
        FactKind.VALUE,
        "111 / 312-B",
    ),
    (
        "ausfuehrungsbeginn",
        "Wann ist mit der Ausführung zu beginnen?",
        FactKind.VALUE,
        "131 § 1",
    ),
    (
        "fertigstellung",
        "Bis wann ist die Leistung fertigzustellen?",
        FactKind.VALUE,
        "131 § 1",
    ),
    ("vertragsstrafe", "Ist eine Vertragsstrafe vereinbart?", FactKind.YES_NO, "131"),
    (
        "sicherheit_vertragserfuellung",
        "Wie hoch ist die Sicherheit für die Vertragserfüllung?",
        FactKind.VALUE,
        "131",
    ),
    (
        "sicherheit_maengel",
        "Wie hoch ist die Sicherheit für Mängelansprüche?",
        FactKind.VALUE,
        "131",
    ),
    (
        "stoffpreisgleitklausel",
        "Gilt eine Stoffpreisgleitklausel?",
        FactKind.YES_NO,
        "131 / 132",
    ),
    (
        "unterlagen_mit_angebot",
        "Welche Unterlagen sind mit dem Angebot einzureichen?",
        FactKind.LIST,
        "109 / 317-B",
    ),
)


def default_facts(tender: str) -> FactFile:
    return FactFile(
        tender=tender,
        facts=[
            Fact(key=key, question=question, kind=kind)
            for key, question, kind, _ in FACT_TEMPLATES
        ],
    )


def facts_to_rows(facts: FactFile) -> list[dict[str, Any]]:
    return [
        {
            COL_KEY: fact.key,
            COL_QUESTION: fact.question,
            COL_KIND: fact.kind.value,
            COL_GOLD: gold_to_text(fact.gold),
            COL_PDF: fact.source.pdf if fact.source else None,
            COL_PAGE: fact.source.page if fact.source else None,
            COL_SECTION: fact.source.section if fact.source else None,
        }
        for fact in facts.facts
    ]


def rows_to_facts(tender: str, rows: list[dict[str, Any]]) -> FactFile:
    facts: list[Fact] = []
    for row in rows:
        key = _text(row.get(COL_KEY))
        if not key:
            continue
        kind = FactKind(row.get(COL_KIND) or FactKind.YES_NO)
        pdf = _text(row.get(COL_PDF))
        page = row.get(COL_PAGE)
        source = (
            FactSource(
                pdf=pdf, page=int(page), section=_text(row.get(COL_SECTION)) or None
            )
            if pdf and page is not None and page == page  # page == page: not NaN
            else None
        )
        facts.append(
            Fact(
                key=key,
                question=_text(row.get(COL_QUESTION)),
                kind=kind,
                gold=text_to_gold(_text(row.get(COL_GOLD)), kind),
                source=source,
            )
        )
    return FactFile(tender=tender, facts=facts)


def gold_to_text(gold: str | list[str] | None) -> str:
    if gold is None:
        return ""
    if isinstance(gold, list):
        return LIST_SEPARATOR.join(gold)
    return gold


def text_to_gold(text: str, kind: FactKind) -> str | list[str] | None:
    if not text:
        return None
    if kind is FactKind.LIST:
        return [
            item.strip() for item in text.split(LIST_SEPARATOR.strip()) if item.strip()
        ]
    return text


def _text(value: Any) -> str:
    if value is None or value != value:  # NaN from the editor
        return ""
    return str(value).strip()
