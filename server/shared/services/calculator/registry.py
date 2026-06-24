"""Loader for the legacy YAML registry knowledge base.

Parked: the kalkulation_v2 catalog engine has superseded this registry for the live
graph. These YAMLs + `stores.py`/`formulas.py` remain only until the P5 cutover
deletes them; `test_calculator_registry` still guards their internal consistency.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from shared.services.calculator.models import Registry

REGISTRY_DIR = Path(__file__).parent / "registry"


def load_registries() -> dict[str, Registry]:
    regs: dict[str, Registry] = {}
    for f in REGISTRY_DIR.glob("*.yaml"):
        reg = Registry.model_validate(yaml.safe_load(f.read_text()))
        regs[reg.work_type] = reg
    return regs


REGISTRIES = load_registries()
