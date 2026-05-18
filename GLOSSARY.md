# Glossary

This glossary defines the German construction-domain terms used throughout Roadbuilders Assistant. The audience is a developer, code reviewer, or AI coding agent who needs enough domain context to navigate the codebase and surrounding documentation without losing track of what a term refers to. It is not exhaustive about German road construction — only the terms that recur in the system, or that a developer will see in test data and example documents.

Where a plural form is non-obvious, it is given in parentheses.

## Procurement and Project Lifecycle

**Vergabe** — Public procurement. The formal process by which a public Auftraggeber awards a construction contract. The "Vergabe" in "Straßenbau Projekt Vergabe" refers to this process.

**Straßenbau** — Road construction. The construction domain this system targets, as opposed to building construction (Hochbau).

**Auftraggeber** — The contracting authority. The public body issuing the tender (e.g., a Bundesland's road authority, a Kommune, a Landratsamt). The party who will sign the contract and pay for the work.

**Auftragnehmer** — The contractor. The construction company that wins the tender and performs the work. Roadbuilders Assistant is used by the prospective Auftragnehmer during the bid phase.

**Angebot** — A bid or offer. The Auftragnehmer's response to a tender, consisting of priced LV items and supporting documents.

**Abgabetermin** — The bid submission deadline. A hard, legally binding deadline; missing it disqualifies the bid.

**Submission** / **Submissionstermin** — The moment bids are opened, after the Abgabetermin. Bids cannot be modified afterward.

**Zuschlag** — The award. The Auftraggeber's decision to accept a specific bid and enter into a contract with that bidder.

**VOB** — Vergabe- und Vertragsordnung für Bauleistungen. The German procurement and contracting code for construction work. Composed of three parts: VOB/A (procurement rules), VOB/B (general contract terms), VOB/C (general technical specifications). Most public road tenders reference VOB/B and VOB/C in their Vertragsbedingungen.

**Vergabestelle** — Procurement office. The administrative arm of the Auftraggeber that runs the tender process. Mostly out of scope for this system; mentioned because it appears on tender cover pages.

## The Tender Document Set

**Baubeschreibung** — Project description. A prose document describing the work to be performed, site conditions, sequencing constraints, and project context. Sets expectations that constrain how the LV items must be priced.

**Leistungsverzeichnis** (LV) — Bill of services. A structured list of all work items to be priced, organised by Position. The contractually binding pricing document. The LV is the system's central artifact: it exists in two forms in a tender — as structured GAEB data (D83 or X83) and as a contractually binding LV PDF.

**Vertragsbedingungen** — General contract terms. Standard contract conditions, usually referencing VOB/B.

**Besondere Vertragsbedingungen** (BVB) — Special contract terms. Project-specific contract clauses that supplement or modify the general Vertragsbedingungen. Often contain the highest-impact clauses for cost calculation: penalty schedules, retention terms, warranty extensions, and similar.

**Zusätzliche Technische Vertragsbedingungen** (ZTV) — Additional technical contract terms. Project-specific technical specifications that supplement VOB/C and the general technical standards. Frequently qualify or override the default execution of LV items. These are sometimes embedded in the Baubeschreibung.

**Vorzulegende Unterlagen** — Documents to be submitted. A checklist of artifacts the bidder must include with the Angebot (Eignungsnachweise, references, certificates, sample calculations, and so on). Missing items typically disqualify a bid.

**Baugrundgutachten** — Soil report. The geotechnical investigation of the site, describing soil layers, bearing capacity, groundwater, and contamination findings. Critical for earthworks pricing and risk assessment.

**Baupläne** — Construction drawings. Plan sheets showing layout, profiles, cross-sections, drainage, and details. Not always provided in road tenders; when provided, typically as PDF.

**Karten** — Maps. Site location maps, regional plans, traffic-management plans, environmental overlays. Out of scope for ingestion in the current sprint.

## GAEB and LV Structure

**GAEB** — Gemeinsamer Ausschuss Elektronik im Bauwesen. The committee that defines the standardised electronic data-exchange formats used to transmit Leistungsverzeichnisse between Auftraggeber and bidders.

**D83** — A GAEB exchange phase representing the Angebotsanforderung: the Auftraggeber's request for offers, delivered as a structured file containing the LV without prices. The bidder fills in unit prices and returns a corresponding response phase.

**X83** — The XML-based GAEB file format carrying the D83 phase. Modern tenders are typically delivered as X83 (older ones as flat D83 text). Both represent the same underlying structure: "D83" identifies the phase, "X83" identifies the file format.

**Position** (Pl. Positionen) — A single line item in the LV. The basic unit of pricing. Each Position carries an OZ, a description, a quantity, a unit, and (after pricing) a unit price.

**OZ** — Ordnungszahl. The hierarchical identifier of a Position within the LV (e.g., `01.02.0030`). Used as a stable reference both within the LV and from external documents — the ZTV may reference Position OZs to qualify them.

**Kurztext** — Short text. The brief, one-line description of a Position.

**Langtext** — Long text. The full multi-paragraph description of a Position, often containing the binding execution requirements for that item.

**Menge** — Quantity. The numeric quantity of the item to be performed (e.g., 2,400.00).

**Einheit** — Unit. The unit of measure for the quantity (m, m², m³, t, St, psch).

**Positionstyp** — Position type. Categorises a Position by its pricing and execution semantics. Common types:

- **Normalposition** — A standard priced item; the bid must include it.
- **Bedarfsposition** — A demand position; priced but executed only if needed.
- **Wahlposition** / **Alternativposition** — An alternative to another Position; only one of the alternatives is executed.
- **Eventualposition** — A contingent position; priced for possible execution.
- **Pauschalposition** — A lump-sum Position; priced as a single value rather than unit × quantity.
- **Stundenlohnarbeiten** — Time-and-materials work; billed at hourly rates against a notional budget.

**STLB-Bau** — Standardleistungsbuch Bau. A national catalogue of standardised Position texts. Tender LVs often reference STLB-Bau text numbers; the actual Langtext may be the standard text, a modified version, or a free-form description.

## User Roles

**Kalkulator** (Pl. Kalkulatoren) — Cost calculator. The contracting company employee responsible for reading the tender documents, deciding whether to bid, and producing the priced LV. The primary user of Roadbuilders Assistant.

**Bauleiter** — Site manager / project manager. The contracting company employee responsible for executing a won project on site. In Roadbuilders Assistant, the Bauleiter role becomes meaningful in later phases when site-execution documents are ingested.

**Subunternehmer** (Pl. Subunternehmer) — Subcontractor. A third-party company executing specific Positionen on behalf of the Auftragnehmer (e.g., signage, line marking, specialised earthworks). Subcontractor management is a Capstone-phase concern.

**Lieferant** (Pl. Lieferanten) — Supplier. A third party supplying materials (asphalt, aggregates, concrete, prefab elements). Like Subunternehmer, primarily a Capstone-phase concern.

## Construction-Phase Terms

**Bautagebuch** (Pl. Bautagebücher) — Site diary. The daily log kept by the Bauleiter recording weather, crew, equipment, deliveries, work performed, and incidents. A key source document for Nachträge and disputes. Ingested in Sprint 3.

**Nachtrag** (Pl. Nachträge) — Variation order / change order. A formal addition or modification to the contract scope or price during construction. Routinely arise from soil findings, scope changes, or specification conflicts discovered during execution. A Capstone-phase concern.

**Aufmaß** — Quantity survey / measurement. The formal measurement of work actually performed, used for billing. Out of scope for now; mentioned for completeness.

## Cost and Pricing

**Einheitspreis** (EP) — Unit price. The price per unit of a Position (e.g., €23.45/m²). The Kalkulator's principal output for each Normalposition is its Einheitspreis.

**Gesamtpreis** (GP) — Total price for a Position: Menge × Einheitspreis.

**Angebotssumme** — Total bid sum. The sum of all Position Gesamtpreise plus any lump-sum and surcharge components.

**EFB** — Einheitliche Formblätter. The standardised cost-structure forms used to break out a bid into its cost components (wages, materials, equipment, subcontractor costs, overhead, profit) for transparent review by the Auftraggeber. Required for public tenders above certain thresholds. "Transparent pricing" in the project description refers to producing output suitable for the EFB forms; full EFB generation is a Capstone-phase goal.

**Gewerk** (Pl. Gewerke) — Trade. A category of work executed as a coherent unit by one crew or one specialty (earthworks, asphalt, drainage, signage, etc.). LVs are typically structured so that all Positionen within a hierarchical branch belong to one Gewerk.

## Standards and Regulatory References

These are not directly ingested but appear constantly in the ZTV and Baubeschreibung. Developers will see them referenced in test data and example documents; they do not need to understand the technical content.

**DIN** — Deutsches Institut für Normung. German industrial standards (e.g., DIN 18300 for earthworks). Routinely referenced in Position Langtexte.

**RStO** — Richtlinien für die Standardisierung des Oberbaus von Verkehrsflächen. Standardised design tables for road pavement structures.

**ZTV Asphalt-StB**, **ZTV E-StB**, **ZTV SoB-StB** — Federal-level standard ZTVs for asphalt, earthworks, and unbound base layers respectively. The project-specific ZTV in a tender typically references these and adds or modifies clauses on top.

**RAS** — Richtlinien für die Anlage von Straßen. Road design guidelines covering geometric design, alignment, and intersections.

---

See also `README.md` for the project's functional scope and `ARCHITECTURE.md` for how these concepts map to the system's data model.
