"""Consistency tests for the calculator knowledge base.

The registry YAMLs reference formulas, stores, machine classes and crew norms by
name; a typo only surfaces at runtime as a soft-failed row. These tests walk every
registry and assert each reference resolves, plus spot-check the new area/interlayer
formulas.
"""

from __future__ import annotations

import pytest

from shared.services.calculator.formulas import (
    FORMULA_KOSTENART,
    FORMULAS,
    AreaDurationIn,
    AreaUnitCostIn,
    AreaVolumeIn,
    EmulsionCostIn,
    InterlayerMaterialIn,
    area_unit_cost,
    area_volume,
    duration_by_area_performance,
    emulsion_cost,
    interlayer_material_cost,
)
from shared.services.calculator.graph import load_registries
from shared.services.calculator.models import Registry
from shared.services.calculator.stores import (
    BGL_RATES,
    CREW_NORMS,
    FLEET_AVAILABILITY,
    INTERLAYER_PROPERTIES,
    MATERIAL_PRICES,
    MATERIAL_PROPERTIES,
    MOBILIZATION,
    PERFORMANCE_RATES,
    STORES,
)

ACCESS_CLASSES = ("open", "confined")

EXPECTED_WORK_TYPES = {
    "fss_herstellen",
    "asphalttragschicht_herstellen",
    "asphalteinlage_einbauen",
}


@pytest.fixture(scope="module")
def registries() -> dict[str, Registry]:
    return load_registries()


def _all_param_specs(reg: Registry):
    for dd in reg.derived_drivers:
        yield f"{reg.work_type}:derived:{dd.id}", dd.params
    for op in reg.operations:
        for row in op.requirements:
            yield f"{reg.work_type}:{op.id}:{row.formula}", row.params


def test_all_three_work_types_load(registries):
    assert set(registries) == EXPECTED_WORK_TYPES


def test_every_formula_reference_resolves(registries):
    for reg in registries.values():
        for dd in reg.derived_drivers:
            assert dd.formula in FORMULAS, f"{reg.work_type}:derived:{dd.id}"
        for op in reg.operations:
            for row in op.requirements:
                assert row.formula in FORMULAS, f"{reg.work_type}:{op.id}:{row.goal}"


def test_every_store_call_resolves(registries):
    for reg in registries.values():
        for where, params in _all_param_specs(reg):
            for spec in params.values():
                if spec.from_ == "store":
                    assert spec.call in STORES, f"{where}: store '{spec.call}'"


def test_every_machine_class_is_priced_and_fleeted(registries):
    for reg in registries.values():
        for op in reg.operations:
            for method in op.methods or []:
                assert method.machine_class in BGL_RATES, method.machine_class
                assert method.machine_class in MOBILIZATION, method.machine_class
                assert method.machine_class in FLEET_AVAILABILITY, method.machine_class


def test_every_method_has_crew_and_performance_rates(registries):
    for reg in registries.values():
        for op in reg.operations:
            if not op.methods:
                continue
            uses_perf = any(
                spec.from_ == "store" and spec.call == "performance_rate"
                for row in op.requirements
                for spec in row.params.values()
            )
            for method in op.methods:
                assert method.id in CREW_NORMS, f"{reg.work_type}:{op.id}:{method.id}"
                if uses_perf:
                    for access in ACCESS_CLASSES:
                        key = (op.id, method.id, access)
                        assert key in PERFORMANCE_RATES, key


# Stores keyed by a catalog vocabulary; judgment-driver options must be keys.
KEYED_STORES = {
    "material_property": MATERIAL_PROPERTIES,
    "material_price": MATERIAL_PRICES,
    "interlayer_property": INTERLAYER_PROPERTIES,
}


def test_judgment_options_are_valid_catalog_keys(registries):
    for reg in registries.values():
        options_by_id = {d.id: d.options for d in reg.drivers if d.options}
        for where, params in _all_param_specs(reg):
            for spec in params.values():
                if spec.from_ != "store" or spec.call not in KEYED_STORES:
                    continue
                options = options_by_id.get(spec.args[0]) if spec.args else None
                for opt in options or []:
                    assert opt in KEYED_STORES[spec.call], (
                        f"{where}: option '{opt}' not a {spec.call} key"
                    )


def test_every_cost_row_has_kostenart(registries):
    """Rows without `out` produce EUR; each needs a VHB 223 bucket."""
    for reg in registries.values():
        for op in reg.operations:
            for row in op.requirements:
                if row.out is None:
                    assert row.formula in FORMULA_KOSTENART, (
                        f"{reg.work_type}:{op.id}:{row.formula}"
                    )


def test_fss_materials_support_water_cost(registries):
    fss = registries["fss_herstellen"]
    options = next(d.options for d in fss.drivers if d.id == "material_spec")
    for opt in options:
        assert "moisture_delta" in MATERIAL_PROPERTIES[opt], opt


def test_area_volume():
    assert area_volume(AreaVolumeIn(area_m2=500.0, thickness_cm=10.0))["value"] == 50.0


def test_duration_by_area_performance():
    out = duration_by_area_performance(AreaDurationIn(quantity_m2=900.0, perf_m2_h=450.0))
    assert out == {"value": 2.0, "einheit": "h"}


def test_interlayer_material_cost_applies_overlap():
    interlayer = {"price_eur_m2": 4.80, "overlap_factor": 1.10}
    out = interlayer_material_cost(
        InterlayerMaterialIn(area_m2=100.0, interlayer=interlayer)
    )
    assert out["eur"] == 528.0


def test_emulsion_cost():
    interlayer = {"emulsion_kg_m2": 0.8}
    out = emulsion_cost(
        EmulsionCostIn(area_m2=100.0, interlayer=interlayer, price_eur_kg=0.65)
    )
    assert out["eur"] == 52.0


def test_area_unit_cost():
    assert area_unit_cost(AreaUnitCostIn(area_m2=200.0, rate_eur_m2=0.15))["eur"] == 30.0
