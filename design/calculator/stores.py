"""Deterministic value stores (mocked for the course project).

In production these are versioned database tables fed by Nachkalkulation,
supplier quotes and the BGL. The agent LOOKS VALUES UP here; it never invents
them. Every accessor returns plain data + is registered in STORES so the
registry interpreter can call it by name from a YAML `{from: store, call: ...}`.
"""
from __future__ import annotations

# --- material physics & commercials ------------------------------------------
MATERIAL_PROPERTIES = {
    "FSS 0/32 B2": {
        "bulk_density_t_m3": 2.10,            # installed/compacted density
        "loss": {"standard": 0.04, "elevated": 0.10},
        "moisture_delta": 0.03,               # m3 water per t (base)
    },
}
MATERIAL_PRICES = {        # EUR
    "FSS 0/32 B2": 12.50,  # per t, delivered ab Werk
    "wasser": 2.50,        # per m3
}

# --- machines (BGL-style Verrechnungssaetze, simplified: incl. fuel) ----------
BGL_RATES = {              # EUR / operating hour
    "grader_3d": 145.0, "loader_small": 95.0,
    "roller_7t": 62.0, "plate_500kg": 18.0,
}
MOBILIZATION = {           # transport of the machine to site
    "grader_3d":   {"eur_km": 7.0, "flat_eur": 220.0},
    "loader_small": {"eur_km": 5.0, "flat_eur": 150.0},
    "roller_7t":   {"eur_km": 5.0, "flat_eur": 150.0},
    "plate_500kg": {"eur_km": 1.5, "flat_eur": 40.0},
}

# --- performance rates: the equipment-side sibling of the Aufwandswert --------
# (operation, method, access_class) -> m3/h. Firm gold data from Nachkalkulation.
PERFORMANCE_RATES = {
    ("distribute", "motor_grader_3dgnss", "open"):     60.0,
    ("distribute", "motor_grader_3dgnss", "confined"): 25.0,
    ("distribute", "dozer_loader_grader", "open"):     30.0,
    ("distribute", "dozer_loader_grader", "confined"): 18.0,
    ("compact", "smooth_drum_roller", "open"):         45.0,
    ("compact", "smooth_drum_roller", "confined"):     20.0,
    ("compact", "ruettelplatte", "open"):               9.0,
    ("compact", "ruettelplatte", "confined"):           7.0,
}

# --- crews & labour ------------------------------------------------------------
CREW_NORMS = {  # method -> crew composition bound to the machine hours
    "motor_grader_3dgnss": {"size": 1, "labor_profile": "qualified_operator"},
    "dozer_loader_grader": {"size": 2, "labor_profile": "general"},
    "smooth_drum_roller":  {"size": 1, "labor_profile": "qualified_operator"},
    "ruettelplatte":       {"size": 1, "labor_profile": "general"},
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
FLEET_AVAILABILITY = {  # consulted by method selection (LLM site 3)
    "grader_3d": False,        # not free in the build window -> nudges selection
    "loader_small": True, "roller_7t": True, "plate_500kg": True,
}
CLIMATE_NORMALS = {"default": {"ambient_temp_c": 16.0}}   # stub for tool:climate


# --- accessors (registered; called by the interpreter, never the LLM) ----------
def material_property(spec): return MATERIAL_PROPERTIES[spec]
def material_price(spec): return MATERIAL_PRICES[spec]
def bgl_rate(machine_class): return BGL_RATES[machine_class]
def mobilization_rate(machine_class): return MOBILIZATION[machine_class]
def performance_rate(operation_id, method_id, access_class):
    return PERFORMANCE_RATES[(operation_id, method_id, access_class)]
def crew_norm(method_id): return CREW_NORMS[method_id]
def labor_profile(code): return LABOR_PROFILES[code]
def truck_for_access(access_class): return TRUCKS[access_class]
def test_norm(kind): return TEST_NORMS[kind]
def fleet_availability(): return FLEET_AVAILABILITY
def climate(_project="default"): return CLIMATE_NORMALS["default"]

STORES = {
    "material_property": material_property,
    "material_price": material_price,
    "bgl_rate": bgl_rate,
    "mobilization_rate": mobilization_rate,
    "performance_rate": performance_rate,
    "crew_norm": crew_norm,
    "labor_profile": labor_profile,
    "truck_for_access": truck_for_access,
    "test_norm": test_norm,
}
