"""Deterministic formula registry. The ONLY origin of computed numbers.

Each formula = (Pydantic input schema, pure function). The registry interpreter
validates resolved params against the schema (the completeness gate), then
calls the function. The LLM never sees these - registry rows pre-bind them
by `formula:` id, so the agent executes rows instead of browsing a tool catalog.

Machine-family physics (e.g. a drum-roller pass model) slot in as further
formula ids without touching the agent.
"""
from __future__ import annotations
import math
from pydantic import BaseModel
from stores import labor_profile


# ----------------------------------------------------------------- schemas --
class LayerVolumeIn(BaseModel):
    length_m: float; width_m: float; thickness_cm: float

class OrderTonnageIn(BaseModel):
    volume_m3: float; material: dict; loss_profile: str

class MaterialCostIn(BaseModel):
    tonnage_t: float; price_eur_t: float

class DeliveryCostIn(BaseModel):
    tonnage_t: float; truck: dict; distance_km: float
    speed_kmh: float = 30.0; load_unload_h: float = 0.4

class DurationIn(BaseModel):
    quantity_m3: float; perf_m3_h: float

class EquipmentCostIn(BaseModel):
    hours: float; rate_eur_h: float

class CrewCostIn(BaseModel):
    hours: float; crew: dict

class MobilizationIn(BaseModel):
    distance_km: float; machine: dict

class WaterCostIn(BaseModel):
    tonnage_t: float; material: dict; ambient_temp_c: float; price_eur_m3: float

class ProofTestIn(BaseModel):
    length_m: float; width_m: float; norm: dict


# ---------------------------------------------------------------- functions --
def layer_volume(p: LayerVolumeIn):
    v = p.length_m * p.width_m * (p.thickness_cm / 100.0)
    return {"value": round(v, 2), "einheit": "m3"}

def order_tonnage(p: OrderTonnageIn):
    loss = p.material["loss"][p.loss_profile]
    t = p.volume_m3 * p.material["bulk_density_t_m3"] * (1 + loss)
    return {"value": round(t, 1), "einheit": "t",
            "note": f"density {p.material['bulk_density_t_m3']} t/m3, loss {loss:.0%} ({p.loss_profile})"}

def material_cost(p: MaterialCostIn):
    return {"eur": round(p.tonnage_t * p.price_eur_t, 2)}

def delivery_cost(p: DeliveryCostIn):
    trips = math.ceil(p.tonnage_t / p.truck["payload_t"])
    cycle_h = 2 * p.distance_km / p.speed_kmh + p.load_unload_h
    hours = trips * cycle_h
    return {"eur": round(hours * p.truck["rate_eur_h"], 2),
            "note": f"{trips} trips x {cycle_h:.2f} h @ {p.truck['rate_eur_h']} EUR/h"}

def duration_by_performance(p: DurationIn):
    return {"value": round(p.quantity_m3 / p.perf_m3_h, 2), "einheit": "h"}

def equipment_cost(p: EquipmentCostIn):
    return {"eur": round(p.hours * p.rate_eur_h, 2)}

def crew_cost(p: CrewCostIn):
    lohn = labor_profile(p.crew["labor_profile"])
    return {"eur": round(p.hours * p.crew["size"] * lohn, 2),
            "note": f"{p.crew['size']} x {p.crew['labor_profile']} @ {lohn} EUR/h"}

def machine_mobilization(p: MobilizationIn):
    return {"eur": round(2 * p.distance_km * p.machine["eur_km"] + p.machine["flat_eur"], 2)}

def water_cost(p: WaterCostIn):
    temp_factor = 1.3 if p.ambient_temp_c > 25 else 1.0
    m3 = p.tonnage_t * p.material["moisture_delta"] * temp_factor
    return {"eur": round(m3 * p.price_eur_m3, 2),
            "note": f"{m3:.1f} m3 water (temp factor {temp_factor})"}

def proof_test_cost(p: ProofTestIn):
    n = math.ceil(p.length_m * p.width_m / p.norm["area_per_test_m2"])
    return {"eur": round(n * p.norm["eur_per_test"], 2), "note": f"{n} tests"}


FORMULAS = {
    "layer_volume": (LayerVolumeIn, layer_volume),
    "order_tonnage": (OrderTonnageIn, order_tonnage),
    "material_cost": (MaterialCostIn, material_cost),
    "delivery_cost": (DeliveryCostIn, delivery_cost),
    "duration_by_performance": (DurationIn, duration_by_performance),
    "equipment_cost": (EquipmentCostIn, equipment_cost),
    "crew_cost": (CrewCostIn, crew_cost),
    "machine_mobilization": (MobilizationIn, machine_mobilization),
    "water_cost": (WaterCostIn, water_cost),
    "proof_test_cost": (ProofTestIn, proof_test_cost),
}
