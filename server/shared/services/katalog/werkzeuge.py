"""The katalog_chat agent's tool surface — the read tools T1–T34 (§3, incl. the ontology lookup).

Each tool is a thin `@tool` wrapper: it opens a short-lived connection, delegates to `LeseModell`
(all query logic lives there, §1.3), and returns a `content_and_artifact` pair — a compact JSON
string the LLM reads plus the same dict as the artifact the chat UI renders. The tool name equals the
`LeseModell` method it calls, so the numbered §3 list and the code stay in lockstep. Every tool is
read-only by construction: this module imports only the read layer, never the write service
(asserted by the read-only import-graph test, §10.5).
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import BaseTool, tool
from sqlalchemy.ext.asyncio import AsyncEngine

from shared.services.katalog.lese_modell import LeseModell


def katalog_werkzeuge(engine: AsyncEngine) -> list[BaseTool]:
    """Build the read-tool list bound to `engine`; each call opens its own short-lived connection."""

    async def ausfuehren(methode: str, **kwargs: Any) -> tuple[str, dict[str, Any]]:
        async with engine.connect() as conn:
            ergebnis = await getattr(LeseModell(conn), methode)(**kwargs)
        return json.dumps(ergebnis, ensure_ascii=False), ergebnis

    # --- Meta and search --------------------------------------------------- #
    @tool(response_format="content_and_artifact")
    async def katalog_uebersicht() -> tuple[str, dict[str, Any]]:
        """Überblick über den Katalog: Anzahl je Entität, Katalog-Stand (letzte Änderung mit
        Zeitpunkt und Benutzer) und Anzahl offener Entwürfe."""
        return await ausfuehren("katalog_uebersicht")

    @tool(response_format="content_and_artifact")
    async def suche_katalog(
        text: str, entitaeten: list[str] | None = None, limit: int | None = None
    ) -> tuple[str, dict[str, Any]]:
        """Lexikalische Rangsuche über alle Entitäten (Code, Name, Bezeichnung, Beschreibung).
        `entitaeten` schränkt optional auf bestimmte Entitätstypen ein. Liefert
        (entitaet, schluessel, name, score). Keine Semantik — bei Fehltreffer umformulieren."""
        return await ausfuehren("suche_katalog", text=text, entitaeten=entitaeten, limit=limit)

    @tool(response_format="content_and_artifact")
    async def zeige_dsl_funktionen() -> tuple[str, dict[str, Any]]:
        """Die Formelsprache (DSL): erlaubte Operatoren, Vergleiche, Ternär-Bedingung und die
        Funktions-Whitelist mit je einer Kurzbedeutung und einem Beispiel."""
        return await ausfuehren("zeige_dsl_funktionen")

    # --- Leistungen -------------------------------------------------------- #
    @tool(response_format="content_and_artifact")
    async def liste_leistungen(
        filter_text: str | None = None, einheit: str | None = None,
        status: str = "aktiv", limit: int | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """Leistungen auflisten: Code, Name, Einheit, Anzahl Bauverfahren-Kandidaten. Optional nach
        Freitext oder Einheit filtern."""
        return await ausfuehren(
            "liste_leistungen", filter_text=filter_text, einheit=einheit, status=status, limit=limit
        )

    @tool(response_format="content_and_artifact")
    async def zeige_leistung(code: str) -> tuple[str, dict[str, Any]]:
        """Eine Leistung im Detail: Bezeichnung, standard_kennung, Einheit und die geordneten
        Bauverfahren-Kandidaten (erster = Standard)."""
        return await ausfuehren("zeige_leistung", code=code)

    # --- Bauverfahren ------------------------------------------------------ #
    @tool(response_format="content_and_artifact")
    async def liste_bauverfahren(
        filter_text: str | None = None, status: str = "aktiv", limit: int | None = None
    ) -> tuple[str, dict[str, Any]]:
        """Bauverfahren auflisten: Code, Name, Anzahl Vorgänge, Anzahl Leistungen die es nutzen."""
        return await ausfuehren(
            "liste_bauverfahren", filter_text=filter_text, status=status, limit=limit
        )

    @tool(response_format="content_and_artifact")
    async def zeige_bauverfahren(code: str) -> tuple[str, dict[str, Any]]:
        """Ein Bauverfahren im Detail: die geordnete Vorgangskette (Code, Name, Geräteklasse,
        Kostenarten) und rückwärts die Leistungen, die darauf abbilden."""
        return await ausfuehren("zeige_bauverfahren", code=code)

    @tool(response_format="content_and_artifact")
    async def finde_bauverfahren_mit_vorgang(vorgang_code: str) -> tuple[str, dict[str, Any]]:
        """Alle Bauverfahren, die einen bestimmten Vorgang enthalten — mit seiner Position in der
        Kette. Die Rückwärtskante der Vorgangskette."""
        return await ausfuehren("finde_bauverfahren_mit_vorgang", vorgang_code=vorgang_code)

    # --- Vorgänge ---------------------------------------------------------- #
    @tool(response_format="content_and_artifact")
    async def liste_vorgaenge(
        ausfuehrungsart_code: str | None = None, betriebsart_code: str | None = None,
        filter_text: str | None = None, status: str = "aktiv", limit: int | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """Vorgänge auflisten, optional gefiltert nach Geräteklasse (ausfuehrungsart_code) und/oder
        Betriebsart (betriebsart_code)."""
        return await ausfuehren(
            "liste_vorgaenge", ausfuehrungsart_code=ausfuehrungsart_code,
            betriebsart_code=betriebsart_code, filter_text=filter_text, status=status, limit=limit,
        )

    @tool(response_format="content_and_artifact")
    async def zeige_vorgang(code: str) -> tuple[str, dict[str, Any]]:
        """Ein Vorgang im Detail: Geräteklasse, Betriebsart, leistung_instanz, kosten_bindung und
        die Rechnung — die benannten Mengen-/Kurven-Instanzen sowie die Kostenzeilen je Kostenart
        (je mit instanziierter Basisformel + Bindungen) plus die enthaltenden Bauverfahren."""
        return await ausfuehren("zeige_vorgang", code=code)

    # --- Geräteklassen / Betriebsarten / -kategorien ----------------------- #
    @tool(response_format="content_and_artifact")
    async def liste_ausfuehrungsarten(
        filter_text: str | None = None, status: str = "aktiv", limit: int | None = None
    ) -> tuple[str, dict[str, Any]]:
        """Geräteklassen (Ausführungsarten) auflisten: Code, Name, Gerätebezug, Anzahl Maschinen,
        Anzahl Vorgänge."""
        return await ausfuehren(
            "liste_ausfuehrungsarten", filter_text=filter_text, status=status, limit=limit
        )

    @tool(response_format="content_and_artifact")
    async def zeige_ausfuehrungsart(code: str) -> tuple[str, dict[str, Any]]:
        """Eine Geräteklasse im Detail plus beide Rückwärtskanten: Maschinen, die diesen Slot füllen,
        und Vorgänge, die sie verlangen."""
        return await ausfuehren("zeige_ausfuehrungsart", code=code)

    @tool(response_format="content_and_artifact")
    async def liste_betriebskategorien(
        status: str = "aktiv", limit: int | None = None
    ) -> tuple[str, dict[str, Any]]:
        """Betriebskategorien auflisten, je mit Anzahl der Betriebsarten."""
        return await ausfuehren("liste_betriebskategorien", status=status, limit=limit)

    @tool(response_format="content_and_artifact")
    async def liste_betriebsarten(
        kategorie_code: str | None = None, filter_text: str | None = None,
        status: str = "aktiv", limit: int | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """Betriebsarten auflisten, optional auf eine Betriebskategorie eingegrenzt."""
        return await ausfuehren(
            "liste_betriebsarten", kategorie_code=kategorie_code, filter_text=filter_text,
            status=status, limit=limit,
        )

    @tool(response_format="content_and_artifact")
    async def zeige_betriebsart(code: str) -> tuple[str, dict[str, Any]]:
        """Eine Betriebsart im Detail plus Rückwärtskanten: Maschinen mit einem Leistungsprofil dafür
        und Vorgänge, die sie auswählen."""
        return await ausfuehren("zeige_betriebsart", code=code)

    # --- Maschinen --------------------------------------------------------- #
    @tool(response_format="content_and_artifact")
    async def liste_maschinen(
        ausfuehrungsart_code: str | None = None, betriebsart_code: str | None = None,
        filter_text: str | None = None, status: str = "aktiv", limit: int | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """Maschinen auflisten, optional gefiltert nach Geräteklasse (ausfuehrungsart_code) und/oder
        nach einer beherrschten Betriebsart (betriebsart_code)."""
        return await ausfuehren(
            "liste_maschinen", ausfuehrungsart_code=ausfuehrungsart_code,
            betriebsart_code=betriebsart_code, filter_text=filter_text, status=status, limit=limit,
        )

    @tool(response_format="content_and_artifact")
    async def zeige_maschine(code: str) -> tuple[str, dict[str, Any]]:
        """Eine Maschine im Detail: Hersteller/Modell, Geräteklasse, der Eigenschafts-Beutel (Wert,
        Einheit, Beleg) und die Leistungsprofile je Betriebsart (Produktivität + Einheit)."""
        return await ausfuehren("zeige_maschine", code=code)

    # --- Baustoffe --------------------------------------------------------- #
    @tool(response_format="content_and_artifact")
    async def liste_baustoffe(
        kategorie: str | None = None, koernung: str | None = None,
        filter_text: str | None = None, status: str = "aktiv", limit: int | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """Baustoffe auflisten: Code, Name, Kategorie, Körnung, Einheit, Basispreis. Optional nach
        Kategorie, Körnung oder Freitext filtern."""
        return await ausfuehren(
            "liste_baustoffe", kategorie=kategorie, koernung=koernung, filter_text=filter_text,
            status=status, limit=limit,
        )

    @tool(response_format="content_and_artifact")
    async def liste_baustoff_kategorien() -> tuple[str, dict[str, Any]]:
        """Die (losen) Baustoff-Kategorien mit ihrer jeweiligen Anzahl Baustoffe."""
        return await ausfuehren("liste_baustoff_kategorien")

    @tool(response_format="content_and_artifact")
    async def zeige_baustoff(code: str) -> tuple[str, dict[str, Any]]:
        """Ein Baustoff im Detail: Eigenschaften (Rohdichte, Verdichtungsfaktor, Körnung, Einheit),
        Basispreis(e), Anzahl führender Lieferanten und die Stammdaten-Variablen, die auf seine
        Eigenschaften brücken."""
        return await ausfuehren("zeige_baustoff", code=code)

    @tool(response_format="content_and_artifact")
    async def finde_lieferanten_fuer_baustoff(
        baustoff_code: str, stichtag: str | None = None
    ) -> tuple[str, dict[str, Any]]:
        """Alle Lieferanten mit gültigem Werkspreis (ab Werk) für einen Baustoff am Stichtag, sortiert
        nach Preis, mit Standort. `stichtag` als ISO-Datum, Standard heute."""
        return await ausfuehren(
            "finde_lieferanten_fuer_baustoff", baustoff_code=baustoff_code, stichtag=stichtag
        )

    # --- Lieferanten & Preise ---------------------------------------------- #
    @tool(response_format="content_and_artifact")
    async def liste_lieferanten(
        filter_text: str | None = None, ort: str | None = None,
        status: str = "aktiv", limit: int | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """Lieferanten auflisten: Code, Name, Standort, Anzahl Baustoffe im Sortiment. Optional nach
        Freitext oder Ort filtern."""
        return await ausfuehren(
            "liste_lieferanten", filter_text=filter_text, ort=ort, status=status, limit=limit
        )

    @tool(response_format="content_and_artifact")
    async def zeige_lieferant(code: str) -> tuple[str, dict[str, Any]]:
        """Ein Lieferant im Detail: Standort/Koordinaten und das Sortiment, gruppiert nach
        Baustoff-Kategorie."""
        return await ausfuehren("zeige_lieferant", code=code)

    @tool(response_format="content_and_artifact")
    async def zeige_preise(
        lieferant_code: str | None = None, baustoff_code: str | None = None,
        stichtag: str | None = None, mit_historie: bool = False,
    ) -> tuple[str, dict[str, Any]]:
        """Rohe Preiszeilen mit Gültigkeitsbereich; nach Lieferant und/oder Baustoff filterbar.
        `mit_historie=true` schließt abgelaufene Zeilen ein; `stichtag` als ISO-Datum, Standard heute."""
        return await ausfuehren(
            "zeige_preise", lieferant_code=lieferant_code, baustoff_code=baustoff_code,
            stichtag=stichtag, mit_historie=mit_historie,
        )

    # --- Formeln & Variablen ----------------------------------------------- #
    @tool(response_format="content_and_artifact")
    async def liste_formeln(
        filter_text: str | None = None,
        status: str = "aktiv", limit: int | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """Die Basisformeln auflisten: Name, Einheit, Beschreibung, deklarierte Parameter, Ausdruck.
        `filter_text` matcht Name, Ausdruck oder Beschreibung."""
        return await ausfuehren(
            "liste_formeln", filter_text=filter_text, status=status, limit=limit,
        )

    @tool(response_format="content_and_artifact")
    async def zeige_formel(name: str) -> tuple[str, dict[str, Any]]:
        """Eine Basisformel im Detail: roher Ausdruck + LaTeX-Darstellung + Legende über ihre
        DEKLARIERTEN Parameter (je mit Einheit, Beschreibung, Standard) und rückwärts die Vorgänge,
        die sie instanziieren."""
        return await ausfuehren("zeige_formel", name=name)

    @tool(response_format="content_and_artifact")
    async def liste_variablen(
        gruppe: str | None = None, filter_text: str | None = None,
        status: str = "aktiv", limit: int | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """Variablen auflisten: Name, Gruppe, Bezeichnung, Einheit, Datentyp. `gruppe` ∈
        stammdaten | kontext."""
        return await ausfuehren(
            "liste_variablen", gruppe=gruppe, filter_text=filter_text, status=status, limit=limit
        )

    @tool(response_format="content_and_artifact")
    async def zeige_variable(name: str) -> tuple[str, dict[str, Any]]:
        """Eine Variable im Detail: Definition, Einheit, Datentyp, die Auflösungs-Kaskade (je Schritt
        Methode/Prompt/Schwelle/Pfad/Konstante) und der aktuelle KONSTANTE-Wert, falls vorhanden."""
        return await ausfuehren("zeige_variable", name=name)

    @tool(response_format="content_and_artifact")
    async def erklaere_variable(name: str) -> tuple[str, dict[str, Any]]:
        """Wie sich eine Variable auflöst — ihr Kaskaden-Blatt: KONSTANTE (ein Satz), STAMMDATEN
        (Brücke auf ein Baustoff-Feld) oder eingabe (situativer kontext-Wert). Die Herleitung einer
        Kostenzeile aus Basisformeln steht auf der Vorgang-Rechnung (zeige_vorgang)."""
        return await ausfuehren("erklaere_variable", name=name)

    @tool(response_format="content_and_artifact")
    async def verwendung_von_variable(name: str) -> tuple[str, dict[str, Any]]:
        """Vollständige Verwendung (where-used): Vorgänge, deren Rechnung sie binden (als Quelle
        einer Instanz oder als Maschinen-Override-Satz in kosten_bindung), samt Rollen, und Globale
        mit ziel_variable darauf. Das Impact-Analyse-Primitiv vor einer Änderung."""
        return await ausfuehren("verwendung_von_variable", name=name)

    # --- Globale Variablen ------------------------------------------------- #
    @tool(response_format="content_and_artifact")
    async def liste_globale_variablen(limit: int | None = None) -> tuple[str, dict[str, Any]]:
        """Die projektweiten Globalen Variablen: Name, Bezeichnung, erforderlich, ist_standort,
        ziel_variable, RAG-Prompt."""
        return await ausfuehren("liste_globale_variablen", limit=limit)

    # --- Ontologie-Lookup (Rezept-Compiler) -------------------------------- #
    @tool(response_format="content_and_artifact")
    async def ontologie_lookup(query: str, limit: int | None = None) -> tuple[str, dict[str, Any]]:
        """„Wo lebt dieser Eingang?" — der Kern des Rezept-Kompilierens. Für einen Bedarf in
        natürlicher Sprache („Dieselpreis", „Leistung Fräsen bei Tiefe", „Dichte Asphalt") liefert
        das Werkzeug die passenden **Basisformeln** (zum Instanziieren, mit Parametern), die passenden
        **Variablen** (bindbare Quellen), die **Bindungsgrammatik** (kontext./stammdaten./baustoff./
        formel.) und das **Mengengerüst** (dimensionsändernde Formeln zum Verketten). Erst hiermit
        suchen, dann binden — statt eine Formel oder Variable neu zu münzen."""
        return await ausfuehren("ontologie_lookup", query=query, limit=limit)

    # --- Lifecycle & Audit ------------------------------------------------- #
    @tool(response_format="content_and_artifact")
    async def zeige_historie(entitaet: str, schluessel: str) -> tuple[str, dict[str, Any]]:
        """Alle Versionen eines Eintrags (Version, Status, Benutzer, gueltig_ab/bis) — die SCD-2-
        Zeitachse. `entitaet` ist der Entitätstyp (z. B. leistungen, formeln, baustoffe)."""
        return await ausfuehren("zeige_historie", entitaet=entitaet, schluessel=schluessel)

    @tool(response_format="content_and_artifact")
    async def liste_entwuerfe() -> tuple[str, dict[str, Any]]:
        """Offene Entwurfs-Bundles, gruppiert nach Bundle, Entität und Autor."""
        return await ausfuehren("liste_entwuerfe")

    return [
        katalog_uebersicht,
        suche_katalog,
        zeige_dsl_funktionen,
        liste_leistungen,
        zeige_leistung,
        liste_bauverfahren,
        zeige_bauverfahren,
        finde_bauverfahren_mit_vorgang,
        liste_vorgaenge,
        zeige_vorgang,
        liste_ausfuehrungsarten,
        zeige_ausfuehrungsart,
        liste_betriebskategorien,
        liste_betriebsarten,
        zeige_betriebsart,
        liste_maschinen,
        zeige_maschine,
        liste_baustoffe,
        liste_baustoff_kategorien,
        zeige_baustoff,
        finde_lieferanten_fuer_baustoff,
        liste_lieferanten,
        zeige_lieferant,
        zeige_preise,
        liste_formeln,
        zeige_formel,
        liste_variablen,
        zeige_variable,
        erklaere_variable,
        verwendung_von_variable,
        liste_globale_variablen,
        ontologie_lookup,
        zeige_historie,
        liste_entwuerfe,
    ]
