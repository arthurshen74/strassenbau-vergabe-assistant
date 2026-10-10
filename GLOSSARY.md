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

**Maßnahme** — The construction measure a tender is about, i.e. the project itself (e.g. "B 247 OD Mühlhausen, Deckenerneuerung"). Stored as the project name; identified by its **Maßnahmenummer**, the Auftraggeber's internal project number.

**Vergabenummer** — The procurement reference under which a Vergabe is published and bids are submitted. Stored as `vergabe_id` on the project. One Maßnahme can be tendered under several Vergabenummern (Lose, re-tenders).

**Bauleistung** — The contract name: the description of the construction work being awarded, as printed on the tender cover page (Aufforderung zur Abgabe eines Angebots). Narrower than the Maßnahme when only part of it is tendered.

## The Tender Document Set

**Baubeschreibung** — Project description. A prose document describing the work to be performed, site conditions, sequencing constraints, and project context. Sets expectations that constrain how the LV items must be priced.

**Leistungsverzeichnis** (LV) — Bill of services. A structured list of all work items to be priced, organised by Position. The contractually binding pricing document. The LV is the system's central artifact: it exists in two forms in a tender — as structured GAEB data (D83 or X83) and as a contractually binding LV PDF. A project can carry several LV files, each ingested as its own LV document (e.g. the same LV as X83 and D83, or one LV per Los).

**Vertragsbedingungen** — General contract terms. Standard contract conditions, usually referencing VOB/B.

**Besondere Vertragsbedingungen** (BVB) — Special contract terms. Project-specific contract clauses that supplement or modify the general Vertragsbedingungen. Often contain the highest-impact clauses for cost calculation: penalty schedules, retention terms, warranty extensions, and similar.

**Zusätzliche Technische Vertragsbedingungen** (ZTV) — Additional technical contract terms. Project-specific technical specifications that supplement VOB/C and the general technical standards. Frequently qualify or override the default execution of LV items. These are sometimes embedded in the Baubeschreibung.

**Vorzulegende Unterlagen** — Documents to be submitted. A checklist of artifacts the bidder must include with the Angebot (Eignungsnachweise, references, certificates, sample calculations, and so on). Missing items typically disqualify a bid.

**Baugrundgutachten** — Soil report. The geotechnical investigation of the site, describing soil layers, bearing capacity, groundwater, and contamination findings. Critical for earthworks pricing and risk assessment.

**Baupläne** — Construction drawings. Plan sheets showing layout, profiles, cross-sections, drainage, and details. Not always provided in road tenders; when provided, typically as PDF.

**Karten** — Maps. Site location maps, regional plans, traffic-management plans, environmental overlays. Distinct from these tender documents, the system also renders its own site and route maps via geocoding in chat and calculation.

## GAEB and LV Structure

**GAEB** — Gemeinsamer Ausschuss Elektronik im Bauwesen. The committee that defines the standardised electronic data-exchange formats used to transmit Leistungsverzeichnisse between Auftraggeber and bidders.

**D83** — A GAEB exchange phase representing the Angebotsanforderung: the Auftraggeber's request for offers, delivered as a structured file containing the LV without prices. The bidder fills in unit prices and returns a corresponding response phase.

**X83** — The XML-based GAEB file format carrying the D83 phase. Modern tenders are typically delivered as X83 (older ones as flat D83 text). Both represent the same underlying structure: "D83" identifies the phase, "X83" identifies the file format.

**Position** (Pl. Positionen) — A single line item in the LV. The basic unit of pricing. Each Position carries an OZ, a description, a quantity, a unit, and (after pricing) a unit price.

**OZ** — Ordnungszahl. The hierarchical identifier of a Position within the LV (e.g., `01.02.0030`). Used as a stable reference both within the LV and from external documents — the ZTV may reference Position OZs to qualify them.

**Kurztext** — Short text. The brief, one-line description of a Position.

**Langtext** — Long text. The full multi-paragraph description of a Position, often containing the binding execution requirements for that item.

**Menge** — Quantity. The numeric quantity of the item to be performed (e.g., 2,400.00).

**Einheit** — Unit. The unit of measure for the quantity (m, m², m³, t, St = Stück/piece, psch = pauschal/lump sum).

**Positionstyp** — Position type. Categorises a Position by its pricing and execution semantics. Common types:

- **Normalposition** — A standard priced item; the bid must include it.
- **Bedarfsposition** — A demand position; priced but executed only if needed.
- **Wahlposition** / **Alternativposition** — An alternative to another Position; only one of the alternatives is executed.
- **Eventualposition** — A contingent position; priced for possible execution.
- **Pauschalposition** — A lump-sum Position; priced as a single value rather than unit × quantity.
- **Stundenlohnarbeiten** — Time-and-materials work; billed at hourly rates against a notional budget.

**Hinweistext** (Hinweis) — Free text inside the LV hierarchy that is not a Position: no quantity, unit or price. GAEB 90 record `20`, GAEB XML `Remark`. It stands before the part of the LV it refers to; its scope is positional (the innermost enclosing LV-Gruppe, or the whole LV at root level). The parser keeps each one as a `Remark` node and copies the Hinweise in scope onto every following Position's `hinweis`.

**Zusätzlicher Text** — Free text outside the LV hierarchy, at the start (Vortext) or end (Nachtext) of the LV. GAEB 90 `T0`/`T1`/`T9` lines ("Vertragliche Regelungen"), GAEB XML `AddText` before or after the `BoQ`. The spec's home for Vorbemerkungen, Baubeschreibung and Bietererklärungen; applies to the whole LV by construction. The parser keeps each block as an `AddTextBlock`.

**Vorbemerkungen** — Preliminary remarks printed ahead of the LV body (contractual rules, site description, bidder instructions). A document concept, not a GAEB element: realised as a Zusätzlicher Text, or in practice as a leading Hinweistext at the LV root. No GAEB element carries the label "Vorbemerkungen"; viewers supply it.

**Ausführungsbeschreibung** — A description shared by several Positionen (GAEB XML `PerfDescr`), referenced from each Position by `RefPerfNo`. The parser appends it to the `hinweis` of the referencing Positionen.

**STLB-Bau** — Standardleistungsbuch Bau. A national catalogue of standardised Position texts. Tender LVs often reference STLB-Bau text numbers; the actual Langtext may be the standard text, a modified version, or a free-form description.

## User Roles

**Kalkulator** (Pl. Kalkulatoren) — Cost calculator. The contracting company employee responsible for reading the tender documents, deciding whether to bid, and producing the priced LV. The primary user of Roadbuilders Assistant.

**Bauleiter** — Site manager / project manager. The contracting company employee responsible for executing a won project on site. In Roadbuilders Assistant, the Bauleiter role becomes meaningful in later phases when site-execution documents are ingested.

**Subunternehmer** (Pl. Subunternehmer) — Subcontractor. A third-party company executing specific Positionen on behalf of the Auftragnehmer (e.g., signage, line marking, specialised earthworks). Subcontractor management is outside the current scope.

**Lieferant** (Pl. Lieferanten) — Supplier. A third party supplying materials (asphalt, aggregates, concrete, prefab elements). A Katalog entity carrying a location and dated per-Baustoff prices; the calculator ranks Lieferanten by route distance from the Baustelle when pricing material supply.

## Construction-Phase Terms

**Bautagebuch** (Pl. Bautagebücher) — Site diary. The daily log kept by the Bauleiter recording weather, crew, equipment, deliveries, work performed, and incidents. A key source document for Nachträge and disputes. Not part of the current bid-phase scope.

**Nachtrag** (Pl. Nachträge) — Variation order / change order. A formal addition or modification to the contract scope or price during construction. Routinely arise from soil findings, scope changes, or specification conflicts discovered during execution. Nachtrag unit prices are derived from the Urkalkulation (**Nachtragskalkulation**) rather than negotiated from scratch.

**Aufmaß** — Quantity survey / measurement. The formal measurement of work actually performed, used for billing. Out of scope for now; mentioned for completeness.

## Road-Construction Operations and Materials

The Kalkulation subsystem (`server/shared/services/calculator`, the agent harness, plus `server/shared/services/kalkulation_v2`, the costing engine) prices individual road-construction Leistungen defined in the Katalog. These terms name the operations and materials the Katalog encodes, and recur in Position Langtexte.

**Oberbau** — Pavement structure. The bound and unbound layers above the Planum (Tragschichten plus Deckschicht) that carry traffic. Sized per RStO by Belastungsklasse.

**Baustoffgemisch** — Aggregate mix. A graded granular material named by grading band (0/32, 0/45, 0/56) and class (B2/B3, C90/3); the input for unbound layers.

**Tragschicht ohne Bindemittel** (ToB) — Unbound base course. A compacted granular layer with no binder; the umbrella for Frostschutzschicht, Schottertragschicht, and Kies-FSS. Built to ZTV SoB-StB.

**Frostschutzschicht** (FSS) — Frost-protection layer. The lowest unbound base layer (a ToB), built from a Baustoffgemisch to protect the Oberbau against frost heave. The `fss_herstellen` work type.

**Schottertragschicht** (STS) — Crushed-stone base course. An unbound base (ToB) of graded crushed stone (e.g. STS 0/32 C90/3).

**Asphalttragschicht** (ATS) — Asphalt base course. The bound base layer of asphalt mix (e.g. AC 22 T, AC 32 T) beneath the binder and surface courses. The `asphalttragschicht_herstellen` work type.

**Planum** — Formation level. The finished, trimmed top surface of the earthworks/subgrade on which the Oberbau is built; held to a height tolerance (e.g. ±2 cm) and proven by Ev2. The `planum_herstellen` work type.

**Bankett** — Shoulder. The strip alongside the carriageway edge. **Bankettbefestigung** reinforces it with a profiled, compacted mineral mix (gebrochenes Naturgestein) tied into the new Fahrbahnkante. The `bankett_befestigen` work type.

**Dünne Asphaltdeckschicht in Kaltbauweise** (DSK) — Thin cold-laid asphalt surface course (slurry surfacing). A thin wearing course applied cold and metered by mass (Trockenmasse, kg/m²), e.g. DSK 5. The `dsk_herstellen` work type.

**Asphalteinlage** — Asphalt interlayer. A reinforcing grid (Asphaltgittergewebe) or fleece (Asphaltvlies) laid between asphalt layers to retard cracking; bonded with Bitumenemulsion. The `asphalteinlage_einbauen` work type.

**Schichtenverbund** — Interlayer bond. The adhesive bond between adjacent asphalt layers, established by spraying a Bitumenemulsion (Anspritzen / Haftbrücke) before the next layer is laid. The `bitumenemulsion_aufspruehen` work type.

**Bitumenemulsion** — Bituminous emulsion. The bond-coat binder sprayed for Schichtenverbund (e.g. C 70 BP 4-OB per TL BE-StB), dosed in kg/m².

**(Kalt-)Fräsen** — (Cold) milling. Removing asphalt to a set **Frästiefe** (milling depth) and taking up the **Fräsgut** / **Fräsasphalt** (millings) for recycling. The `asphalt_fraesen` work type.

**Längsmarkierung** — Longitudinal road marking (lane and edge lines). Removed by milling, Wasserhochdruck (water-jet), or Feinstfräsen; billed per running metre of removed Strich. The `laengsmarkierung_entfernen` work type.

**Verdichten** / **Verdichtung** — Compaction. Densifying a soil or layer (Walzenzug, Tandemwalze, Rüttelplatte) to a Verdichtungsgrad / Ev2 target. The `boden_verdichten` work type covers subgrade in Einschnitten.

**Unterlage reinigen** — Cleaning the substrate (e.g. a milled or sanitised asphalt surface) before the next layer, typically with a selbstaufnehmende Kehrmaschine. The `unterlage_reinigen` work type.

**Baustelle** — Construction site. In the system, the geocoded project site location (a project-context variable) used for map rendering and supplier route-distance ranking.

**Deponie** (Pl. Deponien) — Disposal site. Where Fräsgut and excavated material are hauled; a project-context variable used when pricing Abtransport and Entsorgung.

**Mischwerk** (Pl. Mischwerke) — Mixing plant. The Lieferant facility that produces asphalt mix; the supply point to which route distance is computed.

## Cost and Pricing

**Einheitspreis** (EP) — Unit price. The price per unit of a Position (e.g., €23.45/m²). The Kalkulator's principal output for each Normalposition is its Einheitspreis.

**Gesamtpreis** (GP) — Total price for a Position: Menge × Einheitspreis.

**Angebotssumme** — Total bid sum. The sum of all Position Gesamtpreise plus any lump-sum and surcharge components.

**EFB** — Einheitliche Formblätter. The standardised cost-structure forms used to break out a bid into its cost components (wages, materials, equipment, subcontractor costs, overhead, profit) for transparent review by the Auftraggeber. Required for public tenders above certain thresholds. "Transparent pricing" in the project description refers to producing output suitable for the EFB forms; full EFB generation is a planned enhancement.

**Gewerk** (Pl. Gewerke) — Trade. A category of work executed as a coherent unit by one crew or one specialty (earthworks, asphalt, drainage, signage, etc.). LVs are typically structured so that all Positionen within a hierarchical branch belong to one Gewerk.

**Teilleistung** (Pl. Teilleistungen) — Partial service / work item. One delimited unit of the contract work; in an LV, each Position describes one Teilleistung. The "T" in EKT.

**EKT** — Einzelkosten der Teilleistungen. The direct costs of a single Teilleistung — wages (Lohn), materials (Stoffe), equipment (Geräte), and other (Sonstiges) — before overhead and profit. The Kalkulation subsystem computes the EKT per Position; they roll up into the Einheitspreis.

**Kostenart** (Pl. Kostenarten) — Cost category. The classic EKT split is Lohn, Stoffe, Geräte, Sonstiges — the columns of VHB Formblatt 223. The calculator's internal `Kostenart` enum works one level finer (Material, Maschine, Antransport, Abtransport, Entsorgung, Lohn) and its output keeps these six categories per cost line; rendering them into the four 223 columns is a planned enhancement.

**Zeitansatz** — Time allowance. Labour hours per unit of a Position (h/Einheit): the crew hours over the whole Position divided by its Menge. The first component of a Formblatt 223 row.

**Bauweise** — Construction method. The specific technique chosen to execute an operation (e.g. Fertiger vs. Handeinbau, Walze vs. Rüttelplatte). In the Katalog this choice is modelled by the Bauverfahren and Betriebsart entities.

**Aufwandswert** — Labour expenditure value. Man-hours required per unit of output (e.g. h/m³) — the firm's productivity benchmark. The calculator's equipment performance rate (output per machine hour) is its machine-side sibling.

**BGL** — Baugeräteliste. The standard catalogue of construction-equipment hourly rates (Verrechnungssätze). The calculator's equipment costs read BGL-style rates per machine class.

**Mittellohn** — Average wage. The blended hourly labour rate including Lohnzusatzkosten (social and ancillary costs), applied to crew hours.

**Nachkalkulation** — Post-calculation. Comparing as-built actual costs against the bid to refine the firm's productivity and price data; the intended feedback source for the Katalog.

**VHB** — Vergabe- und Vertragshandbuch des Bundes. The federal procurement handbook whose Formblätter standardise bid cost breakdowns: 221 (Preisermittlung bei Zuschlagskalkulation), 222 (Preisermittlung bei Kalkulation über die Endsumme), 223 (Aufgliederung der Einheitspreise).

**VHB Formblatt 223** — The form breaking the Einheitspreis into its components (a Zeitansatz plus Lohn / Stoffe / Geräte / Sonstiges per unit, ohne USt). The calculator's EKT output (cost lines per Vorgang and Kostenart, plus the Nachweistabelle) carries everything a 223 row needs; the 223-form rendering itself is a planned enhancement. Closely related to the EFB forms.

**Zuschläge** — The overhead and markup layered onto the EKT to reach the Einheitspreis: Baustellengemeinkosten (site overhead), Allgemeine Geschäftskosten (company overhead), and Wagnis und Gewinn (risk and profit), declared on VHB Formblätter 221/222. Not yet produced by the calculator.

**Urkalkulation** — The original bid calculation: the complete per-Position cost breakdowns standing behind an Angebot. Submitted sealed (on the EFB/VHB forms) and opened only for defined causes — Preisprüfung, Nachtragskalkulation, or unit-price disputes.

**Preisprüfung** — Price examination. The Auftraggeber's check of an abnormally low bid to establish whether the price is auskömmlich (cost-covering) before the contract may be awarded.

## The Kalkulation Katalog

The calculator's reference data is a persisted catalog (`katalog_*` tables in Postgres; models in `server/shared/services/kalkulation_v2`). These are the entity names a developer meets in that code.

**Katalog** — The store of calculation reference data: Leistungen, Bauverfahren, Vorgänge, Ausführungsarten, Betriebskategorien and Betriebsarten, Maschinen, Baustoffe, Lieferanten with their Preise, Formeln, and Variablen. Rows have a draft/active lifecycle (`entwurf`, `aktiv`, `verworfen`, `archiviert`); changes are written as a **Bundle** (one coherent change set), and a single **Stand** row names the catalog version in force. Maintained through the Katalog chat agent.

**Leistung** (Pl. Leistungen) — In the Katalog: the service to be rendered — the classification target the calculator maps a Position onto (often keyed to an STLB-Bau text). A Leistung does not own a construction procedure; the calculator selects a Bauverfahren to fulfil it.

**Bauverfahren** — Construction procedure. An ordered list of Vorgänge that fulfils a Leistung; the Leistung–Bauverfahren mapping records which procedures can fulfil which service.

**Vorgang** (Pl. Vorgänge) — One operation within a Bauverfahren. Carries a **Rechnung**: named quantity/curve Instanzen plus, per Kostenart, one or more cost-line Instanzen — each an instantiation of a Basisformel (see Instanz). Where a machine is involved it also names the Betriebsart and the binding from machine properties to the cost-rate variables.

**Ausführungsart** — Equipment slot. The kind of machine a Vorgang requires; each Maschine declares which Ausführungsart slot it can fill.

**Betriebskategorie** — A grouping of Betriebsarten (e.g. `fraesen`, `verdichtung`).

**Betriebsart** — One operation mode within a Betriebskategorie (e.g. `feinfraesen`); selects which of a machine's productivity profiles applies.

**Maschine** (Pl. Maschinen) — A concrete machine (manufacturer + model) that fills an Ausführungsart slot. Carries a property bag (operating cost, fuel, mob/demob, specs) and per-Betriebsart productivity profiles (Leistungsprofile).

**Baustoff** (Pl. Baustoffe) — Material. Carries Rohdichte (density, t/m³), Verdichtungsfaktor (compaction factor), Körnung (grading), and base prices; supplier-specific dated prices live on the Lieferant.

**Variable** (Pl. Variablen) — A managed calculation input with an ordered resolution cascade (Auflösung): each step is one method — `langtext` (extract from the Position text), `rag` (retrieve from project documents), `hitl` (ask the human), `stammdaten` (master-data lookup), `konstante` (fixed value) — tried top to bottom until one yields an accepted value. Two groups survive: `stammdaten` (rates + Baustoff bridges) and `kontext` (situational inputs incl. the geometry placeholders). Resolved values carry provenance: Quelle (source), Konfidenz (confidence), Beleg (evidence). (The `formel` method/group is retired — computation now lives on the Vorgang Rechnung, not on variables.)

**Formel / Basisformel** (Pl. Formeln) — A **base formula**: one expression in the calculator's restricted DSL over **declared formal parameters** (`{name, einheit, beschreibung}`), written once in canonical units. About 16 cover the whole catalog (e.g. `F_STUNDEN = menge / leistung`, `F_MASCHINE`, `F_KOSTEN_SATZ`, the Mengengerüst formulas). Save-time validation requires closure over the signature, mandatory prose, and rejects a formula structurally identical to an existing base formula.

**Instanz / FormelInstanz** — One application of a Basisformel inside a Vorgang's Rechnung: a dict binding the formula's parameters to source paths (`kontext.<var>`, `stammdaten.<var>`, `baustoff.<feld>`, `formel.<instanz>`, or a literal). Unit scaling (cm→m, kg→t) happens at the binding seam; a dimension change (m³→t) is a Mengengerüst formula, not a binding.

**Mengengerüst** — The quantity-derivation formulas that bridge dimensions (`F_MENGE_VOLUMEN` m³→t, `F_VOLUMEN_FLAECHE` m²→m³, `F_MENGE_ANSATZ` Ansatz→t, …). A recipe chains these instead of doing unit arithmetic inside an expression.

**Ontologie** (calculator) — The layer that tells the recipe compiler where each input lives: the static binding-path grammar + the retrieval-grade `beschreibung` prose on every formula, parameter and variable. Surfaced by the `ontologie_lookup` tool and enforced by bundle validation (mandatory prose, binding-path + unit compatibility, structural formula dedup).

## Standards and Regulatory References

These are not directly ingested but appear constantly in the ZTV and Baubeschreibung. Developers will see them referenced in test data and example documents; they do not need to understand the technical content.

**DIN** — Deutsches Institut für Normung. German industrial standards (e.g., DIN 18300 for earthworks). Routinely referenced in Position Langtexte.

**RStO** — Richtlinien für die Standardisierung des Oberbaus von Verkehrsflächen. Standardised design tables for road pavement structures.

**ZTV Asphalt-StB**, **ZTV E-StB**, **ZTV SoB-StB** — Federal-level standard ZTVs for asphalt, earthworks, and unbound base layers respectively. The project-specific ZTV in a tender typically references these and adds or modifies clauses on top.

**RAS** — Richtlinien für die Anlage von Straßen. Road design guidelines covering geometric design, alignment, and intersections.

**TL BE-StB** — Technische Lieferbedingungen für Bitumenemulsionen. The federal delivery spec naming bitumen-emulsion grades (e.g. C 70 BP 4-OB) used for Schichtenverbund.

**Belastungsklasse** (Bk) — Load class. The traffic-load class per RStO (Bk100 down to Bk0.3) that sizes the Oberbau and constrains material and Bauweise selection. Appears in Langtexte as e.g. "Bk 1,0 bis Bk 3,2".

**Ev2** / **Verformungsmodul** — Deformation modulus. The stiffness of a compacted layer or Planum (in MN/m² ≈ MPa), read from the second loading cycle of the Plattendruckversuch; the acceptance criterion for compaction (e.g. "Ev2 = 45 MPa").

**Plattendruckversuch** — Static plate load test. The field test yielding Ev1/Ev2, used to prove compaction of unbound layers and the Planum.

## System and Infrastructure Terms

These are not domain terms; they recur in the codebase around OpenRouter cost tracking and
project-info extraction.

**OpenRouter credits** — The unit OpenRouter reports `cost` in. Credits are USD-denominated (1 credit = 1 USD), so the `cost` column is treated as USD. Recorded per API call in `openrouter_usage`.

**Token usage** — Per-call token counts returned by OpenRouter: `prompt_tokens`, `completion_tokens`, `total_tokens`, plus `cached_tokens` (prompt tokens served from cache) and `reasoning_tokens` (chat reasoning) where applicable. Shapes differ per endpoint (chat vs embeddings vs rerank).

**Search units** — Cohere's rerank billing unit, returned as `search_units` on rerank responses. Rerank reports no prompt/completion tokens.

**Usage sink** — A small async interface (`UsageSink`) an OpenRouter client emits a `UsageEvent` to after each call. `LoggingUsageSink` logs one line (default); `DatabaseUsageSink` persists to `openrouter_usage`.

**Projektinfo** — The project header fields (Projektname/Maßnahme, Maßnahmenummer, Vergabenummer, Bauleistung, Baustelle, Projektbeschreibung) read from the tender documents after ingestion. Filled by one `project_info_jobs` row per run, which the worker claims once the project's ingest jobs are no longer queued or running; it runs every RAG Query (Projektinfo) and writes only values the documents support. Status and per-field evidence show on the project page, which can also start a re-run.

**RAG Query (Projektinfo)** — A versioned question that fills one project header field (Maßnahme, Maßnahmenummer, Vergabenummer, Bauleistung, Baustelle, Projektbeschreibung) from the ingested tender documents. Stored append-only in `rag_query_versions` per key and language; each version has a `query_text` (the retrieval question, embedded and BM25-matched, so it must be in the document language) and an `answer_instruction` (the output rule for the synthesis LLM). Edited in the RAG Queries view.

---

See also `README.md` for the project's functional scope, `APPLICATION_ARCHITECTURE.md` for how these concepts map to the system's data model, and `AI_ARCHITECTURE.md` for the pipelines and agents that operate on them.
