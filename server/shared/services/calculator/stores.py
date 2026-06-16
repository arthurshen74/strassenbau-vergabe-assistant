"""Deterministic value stores (mocked for the course project).

In production these are versioned database tables fed by Nachkalkulation,
supplier quotes and the BGL. The agent LOOKS VALUES UP here; it never invents
them. Every accessor returns plain data + is registered in STORES so the
registry interpreter can call it by name from a YAML `{from: store, call: ...}`.
"""
from __future__ import annotations

# --- material physics & commercials ------------------------------------------
# The keys are the firm's material catalog. Registries expose them as judgment
# driver options, so the LLM maps Langtext wording onto EXACTLY these keys and
# the interpreter never sees a free-text material spec.
MATERIAL_PROPERTIES = {
    # ungebundene Gemische (ToB nach ZTV SoB-StB); densities installed/compacted,
    # moisture_delta = m3 water per t (base) for compaction conditioning
    "FSS 0/32 B2": {"bulk_density_t_m3": 2.10,
                    "loss": {"standard": 0.04, "elevated": 0.10},
                    "moisture_delta": 0.03},
    "FSS 0/32 B3": {"bulk_density_t_m3": 2.08,
                    "loss": {"standard": 0.04, "elevated": 0.10},
                    "moisture_delta": 0.03},
    "FSS 0/45 B2": {"bulk_density_t_m3": 2.15,
                    "loss": {"standard": 0.04, "elevated": 0.09},
                    "moisture_delta": 0.03},
    "FSS 0/56 B2": {"bulk_density_t_m3": 2.20,
                    "loss": {"standard": 0.03, "elevated": 0.08},
                    "moisture_delta": 0.025},
    "KFS 0/32": {"bulk_density_t_m3": 2.05,                  # Kies-FSS
                 "loss": {"standard": 0.05, "elevated": 0.11},
                 "moisture_delta": 0.035},
    "STS 0/32 C90/3": {"bulk_density_t_m3": 2.15,            # Schottertragschicht
                       "loss": {"standard": 0.04, "elevated": 0.09},
                       "moisture_delta": 0.03},
    "RC-Gemisch 0/45": {"bulk_density_t_m3": 1.95,           # recycled aggregate
                        "loss": {"standard": 0.06, "elevated": 0.13},
                        "moisture_delta": 0.04},
    # Bankettmaterial (gebr. Naturgestein, Mineralgemisch nach ZTV-StB LSBB)
    "Mineralgemisch 0/32 B2": {"bulk_density_t_m3": 2.15,
                               "loss": {"standard": 0.04, "elevated": 0.10},
                               "moisture_delta": 0.03},
    "Mineralgemisch 0/45 B2": {"bulk_density_t_m3": 2.18,
                               "loss": {"standard": 0.04, "elevated": 0.09},
                               "moisture_delta": 0.03},
    "Schotter 0/32 gebr. Naturgestein": {"bulk_density_t_m3": 2.20,
                                         "loss": {"standard": 0.03, "elevated": 0.08},
                                         "moisture_delta": 0.025},
    # Fräsgut (milled-asphalt arisings); loss 0 - order_tonnage is reused purely as
    # volume*in-place-density for the haul tonnage, no Mehrmenge applies.
    "Fräsasphalt": {"bulk_density_t_m3": 2.40,
                    "loss": {"standard": 0.0, "elevated": 0.0}},
    # Dünne Asphaltdeckschicht in Kaltbauweise (DSK); kg_m2 = the firm-standard
    # Einbaumenge (Trockenmasse) for that mix - the application-rate sibling of the
    # Aufwandswert, so the LLM selects the DSK type and never reads the kg/m2.
    "DSK 5": {"kg_m2": 18.0},
    "DSK 8": {"kg_m2": 22.0},
    "DSK 11": {"kg_m2": 28.0},
    # Bitumenemulsionen für Schichtenverbund (Anspritzen); emulsion_kg_m2 = the
    # firm-standard Bindemittelmenge per grade (the application rate, not read from text).
    "C 70 BP 4-OB": {"emulsion_kg_m2": 2.0},
    "C 60 B 1-S": {"emulsion_kg_m2": 0.40},
    "C 67 B 4": {"emulsion_kg_m2": 0.50},
    # Asphaltmischgut (ZTV Asphalt-StB)
    "AC 22 T S": {"bulk_density_t_m3": 2.40,
                  "loss": {"standard": 0.02, "elevated": 0.05}},
    "AC 32 T S": {"bulk_density_t_m3": 2.42,
                  "loss": {"standard": 0.02, "elevated": 0.05}},
    "AC 16 B S": {"bulk_density_t_m3": 2.45,
                  "loss": {"standard": 0.02, "elevated": 0.04}},
    "AC 11 D S": {"bulk_density_t_m3": 2.45,
                  "loss": {"standard": 0.015, "elevated": 0.04}},
}
MATERIAL_PRICES = {        # EUR per t delivered ab Werk/Mischwerk, unless noted
    "FSS 0/32 B2": 12.50,
    "FSS 0/32 B3": 11.20,
    "FSS 0/45 B2": 11.80,
    "FSS 0/56 B2": 11.20,
    "KFS 0/32": 9.80,
    "STS 0/32 C90/3": 14.80,
    "RC-Gemisch 0/45": 7.50,
    "Mineralgemisch 0/32 B2": 13.50,
    "Mineralgemisch 0/45 B2": 12.80,
    "Schotter 0/32 gebr. Naturgestein": 15.50,
    "DSK 5": 350.00,           # DSK mix incl. Bindemittel, ab Werk
    "DSK 8": 330.00,
    "DSK 11": 320.00,
    "C 70 BP 4-OB": 0.72,      # per kg, polymermodifiziert
    "C 60 B 1-S": 0.65,        # per kg
    "C 67 B 4": 0.66,          # per kg
    "AC 22 T S": 96.00,
    "AC 32 T S": 92.00,
    "AC 16 B S": 104.00,
    "AC 11 D S": 118.00,
    "bitumenemulsion": 0.65,  # per kg, C60B1-S
    "wasser": 2.50,        # per m3
}

# --- Asphalteinlagen (interlayer products, ZTV Asphalt-StB) --------------------
INTERLAYER_PROPERTIES = {
    "Asphaltgittergewebe": {"price_eur_m2": 4.80, "emulsion_kg_m2": 0.8,
                            "overlap_factor": 1.10},
    "Asphaltvlies": {"price_eur_m2": 2.20, "emulsion_kg_m2": 1.1,
                     "overlap_factor": 1.08},
}

# --- machines (BGL-style Verrechnungssaetze, simplified: incl. fuel) ----------
BGL_RATES = {              # EUR / operating hour
    "grader_3d": 145.0, "loader_small": 95.0,
    "roller_7t": 62.0, "plate_500kg": 18.0,
    "fertiger": 260.0, "tandem_roller_8t": 75.0, "roller_1_5t": 35.0,
    "verlegegeraet": 65.0, "kleingeraet": 12.0,
    "walzenzug": 85.0,                       # Erd-/Bodenverdichtung
    "kehrmaschine": 70.0,                    # selbstaufnehmend
    "kaltfraese_gross": 320.0, "kaltfraese_klein": 140.0,
    "markierungsfraese": 55.0, "wasserhochdruckgeraet": 110.0, "feinstfraese": 70.0,
    "dsk_fertiger": 180.0,                   # DSK-Einbaugerät (Slurry-Fertiger)
}
MOBILIZATION = {           # transport of the machine to site
    "grader_3d":   {"eur_km": 7.0, "flat_eur": 220.0},
    "loader_small": {"eur_km": 5.0, "flat_eur": 150.0},
    "roller_7t":   {"eur_km": 5.0, "flat_eur": 150.0},
    "plate_500kg": {"eur_km": 1.5, "flat_eur": 40.0},
    "fertiger":    {"eur_km": 9.0, "flat_eur": 350.0},
    "tandem_roller_8t": {"eur_km": 5.0, "flat_eur": 180.0},
    "roller_1_5t": {"eur_km": 2.0, "flat_eur": 60.0},
    "verlegegeraet": {"eur_km": 4.0, "flat_eur": 120.0},
    "kleingeraet": {"eur_km": 1.0, "flat_eur": 30.0},
    "walzenzug": {"eur_km": 5.0, "flat_eur": 170.0},
    "kehrmaschine": {"eur_km": 3.0, "flat_eur": 90.0},
    "kaltfraese_gross": {"eur_km": 9.0, "flat_eur": 400.0},
    "kaltfraese_klein": {"eur_km": 4.0, "flat_eur": 150.0},
    "markierungsfraese": {"eur_km": 2.0, "flat_eur": 80.0},
    "wasserhochdruckgeraet": {"eur_km": 3.0, "flat_eur": 150.0},
    "feinstfraese": {"eur_km": 2.5, "flat_eur": 100.0},
    "dsk_fertiger": {"eur_km": 6.0, "flat_eur": 250.0},
}

# --- performance rates: the equipment-side sibling of the Aufwandswert --------
# (operation, method, access_class) -> output per hour. Firm gold data from
# Nachkalkulation. Unit follows the operation's duration formula: m3/h for the
# volume operations (distribute, compact, pave), m2/h for the area ones (verlegen).
PERFORMANCE_RATES = {
    ("distribute", "motor_grader_3dgnss", "open"):     60.0,
    ("distribute", "motor_grader_3dgnss", "confined"): 25.0,
    ("distribute", "dozer_loader_grader", "open"):     30.0,
    ("distribute", "dozer_loader_grader", "confined"): 18.0,
    ("compact", "smooth_drum_roller", "open"):         45.0,
    ("compact", "smooth_drum_roller", "confined"):     20.0,
    ("compact", "ruettelplatte", "open"):               9.0,
    ("compact", "ruettelplatte", "confined"):           7.0,
    ("pave", "fertiger", "open"):                      80.0,
    ("pave", "fertiger", "confined"):                  25.0,
    ("pave", "asphalt_handeinbau", "open"):             8.0,
    ("pave", "asphalt_handeinbau", "confined"):         5.0,
    ("compact", "tandem_roller", "open"):              60.0,
    ("compact", "tandem_roller", "confined"):          22.0,
    ("compact", "kleinwalze", "open"):                 14.0,
    ("compact", "kleinwalze", "confined"):              9.0,
    ("verlegen", "einlage_maschinell", "open"):       450.0,
    ("verlegen", "einlage_maschinell", "confined"):   180.0,
    ("verlegen", "einlage_manuell", "open"):          140.0,
    ("verlegen", "einlage_manuell", "confined"):       90.0,
    # Boden/Untergrund verdichten (m2/h)
    ("verdichten", "walzenzug", "open"):              800.0,
    ("verdichten", "walzenzug", "confined"):          350.0,
    ("verdichten", "ruettelplatte", "open"):          200.0,
    ("verdichten", "ruettelplatte", "confined"):      120.0,
    # Planum herstellen / feinplanieren (m2/h)
    ("feinplanum", "motor_grader_3dgnss", "open"):     900.0,
    ("feinplanum", "motor_grader_3dgnss", "confined"): 400.0,
    ("feinplanum", "dozer_loader_grader", "open"):     500.0,
    ("feinplanum", "dozer_loader_grader", "confined"): 250.0,
    # Unterlage reinigen (m2/h)
    ("reinigen", "kehrmaschine", "open"):            2500.0,
    ("reinigen", "kehrmaschine", "confined"):        1200.0,
    ("reinigen", "handreinigung_klein", "open"):      400.0,
    ("reinigen", "handreinigung_klein", "confined"):  250.0,
    # Asphalt fräsen (m2/h)
    ("fraesen", "kaltfraese_gross", "open"):          500.0,
    ("fraesen", "kaltfraese_gross", "confined"):      200.0,
    ("fraesen", "kaltfraese_klein", "open"):          150.0,
    ("fraesen", "kaltfraese_klein", "confined"):       90.0,
    # DSK in Kaltbauweise einbauen (m2/h)
    ("dsk_einbau", "dsk_fertiger", "open"):           600.0,
    ("dsk_einbau", "dsk_fertiger", "confined"):       250.0,
    ("dsk_einbau", "dsk_kleingeraet", "open"):        120.0,
    ("dsk_einbau", "dsk_kleingeraet", "confined"):     70.0,
    # Längsmarkierung entfernen (m/h of removed Strich)
    ("markierung_entfernen", "markierung_fraesen", "open"):     400.0,
    ("markierung_entfernen", "markierung_fraesen", "confined"): 250.0,
    ("markierung_entfernen", "wasserhochdruck", "open"):        300.0,
    ("markierung_entfernen", "wasserhochdruck", "confined"):    180.0,
    ("markierung_entfernen", "feinstfraesen", "open"):          350.0,
    ("markierung_entfernen", "feinstfraesen", "confined"):      200.0,
}

# --- crews & labour ------------------------------------------------------------
CREW_NORMS = {  # method -> crew composition bound to the machine hours
    "motor_grader_3dgnss": {"size": 1, "labor_profile": "qualified_operator"},
    "dozer_loader_grader": {"size": 2, "labor_profile": "general"},
    "smooth_drum_roller":  {"size": 1, "labor_profile": "qualified_operator"},
    "ruettelplatte":       {"size": 1, "labor_profile": "general"},
    "fertiger":            {"size": 4, "labor_profile": "general"},
    "asphalt_handeinbau":  {"size": 5, "labor_profile": "general"},
    "tandem_roller":       {"size": 1, "labor_profile": "qualified_operator"},
    "kleinwalze":          {"size": 1, "labor_profile": "general"},
    "einlage_maschinell":  {"size": 3, "labor_profile": "general"},
    "einlage_manuell":     {"size": 4, "labor_profile": "general"},
    "walzenzug":           {"size": 1, "labor_profile": "qualified_operator"},
    "kehrmaschine":        {"size": 1, "labor_profile": "general"},
    "handreinigung_klein": {"size": 2, "labor_profile": "general"},
    "kaltfraese_gross":    {"size": 3, "labor_profile": "general"},
    "kaltfraese_klein":    {"size": 2, "labor_profile": "general"},
    "markierung_fraesen":  {"size": 2, "labor_profile": "general"},
    "wasserhochdruck":     {"size": 2, "labor_profile": "general"},
    "feinstfraesen":       {"size": 2, "labor_profile": "general"},
    "dsk_fertiger":        {"size": 3, "labor_profile": "general"},
    "dsk_kleingeraet":     {"size": 3, "labor_profile": "general"},
}
LABOR_PROFILES = {  # Mittellohn EUR/h incl. Lohnzusatzkosten
    "general": 42.0,
    "qualified_operator": 48.0,   # qualification requirement lives HERE
}

# --- logistics & QA -------------------------------------------------------------
TRUCKS = {  # delivery truck by site access
    "open":     {"payload_t": 24.0, "rate_eur_h": 90.0},
    "confined": {"payload_t": 12.0, "rate_eur_h": 75.0},
}
TEST_NORMS = {
    "plattendruck": {"area_per_test_m2": 250.0, "eur_per_test": 180.0},
}
UNIT_RATES = {  # flat EUR/m2 Verrechnungssaetze for small auxiliary work steps
    "anspritzen": 0.15,    # Aufbringen Bitumenemulsion (Spritzrampe + Bedienung)
}
FLEET_AVAILABILITY = {  # consulted by method selection (LLM site 3)
    "grader_3d": False,        # not free in the build window -> nudges selection
    "loader_small": True, "roller_7t": True, "plate_500kg": True,
    "fertiger": True, "tandem_roller_8t": True, "roller_1_5t": True,
    "verlegegeraet": False,    # nudges einlage selection toward manual / rental
    "kleingeraet": True,
    "walzenzug": True, "kehrmaschine": True,
    "kaltfraese_gross": True, "kaltfraese_klein": True,
    "markierungsfraese": True, "wasserhochdruckgeraet": True, "feinstfraese": True,
    "dsk_fertiger": True,
}
CLIMATE_NORMALS = {"default": {"ambient_temp_c": 16.0}}   # stub for tool:climate


# --- accessors (registered; called by the interpreter, never the LLM) ----------
def material_property(spec): return MATERIAL_PROPERTIES[spec]
def material_price(spec): return MATERIAL_PRICES[spec]
def interlayer_property(spec): return INTERLAYER_PROPERTIES[spec]
def bgl_rate(machine_class): return BGL_RATES[machine_class]
def mobilization_rate(machine_class): return MOBILIZATION[machine_class]
def performance_rate(operation_id, method_id, access_class):
    return PERFORMANCE_RATES[(operation_id, method_id, access_class)]
def crew_norm(method_id): return CREW_NORMS[method_id]
def labor_profile(code): return LABOR_PROFILES[code]
def truck_for_access(access_class): return TRUCKS[access_class]
def test_norm(kind): return TEST_NORMS[kind]
def unit_rate(kind): return UNIT_RATES[kind]
def fleet_availability(): return FLEET_AVAILABILITY
def climate(_project="default"): return CLIMATE_NORMALS["default"]

STORES = {
    "material_property": material_property,
    "material_price": material_price,
    "interlayer_property": interlayer_property,
    "bgl_rate": bgl_rate,
    "mobilization_rate": mobilization_rate,
    "performance_rate": performance_rate,
    "crew_norm": crew_norm,
    "labor_profile": labor_profile,
    "truck_for_access": truck_for_access,
    "test_norm": test_norm,
    "unit_rate": unit_rate,
}
