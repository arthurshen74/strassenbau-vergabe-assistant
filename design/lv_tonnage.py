"""
lv_tonnage.py
=============

LV specification -> purchase tonnage for mineral road-building layers
(Frostschutzschicht, Schottertragschicht, etc.).

The job of this module is to convert a *compacted, in-place* volume taken from an
LV position (typically `abgerechnet nach Auftragsprofilen`) into the *wet tonnage
you actually order from the works* -- and to keep every assumption in that chain
explicit, because most of them are guesses until the Sortenverzeichnis is in hand.

Conversion chain (all factors are physically distinct on purpose):

    volume_m3 (compacted, by profile)
      x  Proctordichte            -> dry solids at 100 % Proctor      [t]
      x  degree_of_compaction     -> dry solids actually in the layer [t]
      x  (1 + delivery_moisture)  -> WET mass to deliver (works bill) [t]
      x  (1 + loss_factor)        -> ORDER tonnage (Mehrverbrauch)    [t]

Unit convention:
    - lengths/areas/volumes: m, m2, m3
    - densities:             t/m3  (== Mg/m3)
    - masses:                t
    - moisture / compaction / loss: dimensionless FRACTIONS (0.05, not 5 %)

Two key design choices, both defensive:
    1. Volume must be COMPACTED. Feeding a loose heap volume into Proctordichte is
       a silent ~20-30 % error, so a LOOSE basis raises instead of guessing.
    2. The result is a breakdown, not a scalar, so you can see which assumption
       moves the number and defend it in the Kalkulation.

Requires Python 3.9+ (uses `from __future__ import annotations`).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

__all__ = [
    "VolumeBasis",
    "ScalarRange",
    "LayerQuantity",
    "MaterialProperties",
    "ProcessAssumptions",
    "MaterialPropertyRange",
    "ProcessRange",
    "TonnageResult",
    "TonnageBand",
    "calculate_order_tonnage",
    "calculate_order_tonnage_band",
]


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------

class VolumeBasis(Enum):
    """How the volume was measured. Only COMPACTED is convertible via Proctordichte."""
    COMPACTED_PROFILE = "auftragsprofile"   # in-place, post-compaction (the usual LV case)
    LOOSE = "lose"                          # uncompacted heap -> needs Schuettdichte, not this tool


@dataclass(frozen=True)
class ScalarRange:
    """A low / expected / high triple for an uncertain scalar assumption."""
    low: float
    expected: float
    high: float

    def __post_init__(self) -> None:
        if not (self.low <= self.expected <= self.high):
            raise ValueError(f"ScalarRange must satisfy low <= expected <= high, got {self!r}")


@dataclass(frozen=True)
class LayerQuantity:
    """Quantities lifted straight from the LV position."""
    volume_m3: float | None = None          # given directly (abgerechnet nach Auftragsprofilen)
    area_m2: float | None = None            # OR derive from area x thickness ...
    thickness_m: float | None = None        # ... Einbaudicke
    basis: VolumeBasis = VolumeBasis.COMPACTED_PROFILE
    lv_position_ref: str | None = None      # e.g. "OZ 01.02.0030" -- traceability


@dataclass(frozen=True)
class MaterialProperties:
    """
    Point estimate of material properties.

    ASSUMED until you have the Sortenverzeichnis, then replace the whole object and
    set `source` so the audit trail back to the real datasheet is preserved.
    """
    proctor_density_t_m3: float = 2.10      # Proctordichte (trocken)
    delivery_moisture: float = 0.05         # w = m_water / m_solids, as delivered from the works
    source: str = "assumed"                 # e.g. "KWN Sortenverz. 2/22, Sorte 21501 (FSS 0/32 gebr.)"


@dataclass(frozen=True)
class ProcessAssumptions:
    """Workmanship / site factors -- not material properties."""
    degree_of_compaction: float = 1.00      # achieved rho_d / Proctordichte; ~1.0 at the required Ev2
    loss_factor: float = 0.05               # Mehrverbrauch (handling + Eindrueck in soft Untergrund)


@dataclass(frozen=True)
class MaterialPropertyRange:
    """Ranged material assumptions for the band variant."""
    proctor_density_t_m3: ScalarRange
    delivery_moisture: ScalarRange
    source: str = "assumed"

    def at(self, level: str) -> MaterialProperties:
        return MaterialProperties(
            proctor_density_t_m3=getattr(self.proctor_density_t_m3, level),
            delivery_moisture=getattr(self.delivery_moisture, level),
            source=self.source,
        )


@dataclass(frozen=True)
class ProcessRange:
    """Ranged process assumptions for the band variant."""
    degree_of_compaction: ScalarRange
    loss_factor: ScalarRange

    def at(self, level: str) -> ProcessAssumptions:
        return ProcessAssumptions(
            degree_of_compaction=getattr(self.degree_of_compaction, level),
            loss_factor=getattr(self.loss_factor, level),
        )


# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TonnageResult:
    """A single point estimate, broken out so every step is inspectable."""
    volume_m3: float
    dry_solids_t: float                     # volume x Proctordichte (100 % Proctor)
    in_place_dry_t: float                   # x degree_of_compaction
    delivered_wet_t: float                  # x (1 + moisture)  <- what the works invoices
    order_t: float                          # x (1 + loss)      <- what you buy
    truckloads: int | None = None

    def __str__(self) -> str:
        lines = [
            f"  volume (compacted):        {self.volume_m3:8.1f} m3",
            f"  dry solids (100% Proctor): {self.dry_solids_t:8.1f} t",
            f"  in-place dry (x DPr):      {self.in_place_dry_t:8.1f} t",
            f"  delivered wet (x moist.):  {self.delivered_wet_t:8.1f} t",
            f"  ORDER (x loss):            {self.order_t:8.1f} t",
        ]
        if self.truckloads is not None:
            lines.append(f"  -> truckloads:             {self.truckloads:8d}")
        return "\n".join(lines)


@dataclass(frozen=True)
class TonnageBand:
    """
    An envelope, not a probability distribution.

    Because order tonnage is a product of factors each monotonically increasing in
    tonnage (density, compaction, moisture, loss), the all-low and all-high corners
    ARE the true min/max of the envelope -- no Monte Carlo needed. If you ever add a
    non-monotonic factor, switch to evaluating all 2**n corners instead.
    """
    low: TonnageResult
    expected: TonnageResult
    high: TonnageResult

    @property
    def order_range_t(self) -> tuple[float, float]:
        return (self.low.order_t, self.high.order_t)

    def __str__(self) -> str:
        lo, hi = self.order_range_t
        return (
            f"ORDER BAND: {lo:.0f} - {hi:.0f} t  (expected {self.expected.order_t:.0f} t)\n"
            f"--- low ---\n{self.low}\n"
            f"--- expected ---\n{self.expected}\n"
            f"--- high ---\n{self.high}"
        )


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------

def _resolve_volume(q: LayerQuantity) -> float:
    """Return the compacted volume in m3, or raise with a clear reason."""
    if q.basis is VolumeBasis.LOOSE:
        raise ValueError(
            "This calculator expects a COMPACTED (Auftragsprofil) volume because it "
            "converts via Proctordichte. A loose volume needs Schuettdichte instead."
        )
    if q.volume_m3 is not None:
        if q.volume_m3 <= 0:
            raise ValueError("volume_m3 must be positive.")
        return q.volume_m3
    if q.area_m2 is not None and q.thickness_m is not None:
        if q.area_m2 <= 0 or q.thickness_m <= 0:
            raise ValueError("area_m2 and thickness_m must be positive.")
        return q.area_m2 * q.thickness_m
    raise ValueError("Provide either volume_m3, or both area_m2 and thickness_m.")


def calculate_order_tonnage(
    quantity: LayerQuantity,
    material: MaterialProperties = MaterialProperties(),
    process: ProcessAssumptions = ProcessAssumptions(),
    truck_capacity_t: float | None = None,
) -> TonnageResult:
    """
    Convert a compacted LV volume into the wet tonnage to order.

    See the module docstring for the full conversion chain. Returns the complete
    breakdown so the headline `order_t` can be audited step by step.
    """
    if material.proctor_density_t_m3 <= 0:
        raise ValueError("proctor_density_t_m3 must be positive.")
    if material.delivery_moisture < 0:
        raise ValueError("delivery_moisture must be >= 0.")
    if process.degree_of_compaction <= 0:
        raise ValueError("degree_of_compaction must be positive.")
    if process.loss_factor < 0:
        raise ValueError("loss_factor must be >= 0.")
    if truck_capacity_t is not None and truck_capacity_t <= 0:
        raise ValueError("truck_capacity_t must be positive when provided.")

    volume = _resolve_volume(quantity)

    dry_solids = volume * material.proctor_density_t_m3
    in_place_dry = dry_solids * process.degree_of_compaction
    delivered_wet = in_place_dry * (1.0 + material.delivery_moisture)
    order = delivered_wet * (1.0 + process.loss_factor)

    truckloads = math.ceil(order / truck_capacity_t) if truck_capacity_t else None

    return TonnageResult(
        volume_m3=volume,
        dry_solids_t=dry_solids,
        in_place_dry_t=in_place_dry,
        delivered_wet_t=delivered_wet,
        order_t=order,
        truckloads=truckloads,
    )


def calculate_order_tonnage_band(
    quantity: LayerQuantity,
    material_range: MaterialPropertyRange,
    process_range: ProcessRange,
    truck_capacity_t: float | None = None,
) -> TonnageBand:
    """
    Run the point calculation at low / expected / high assumptions and return the band.

    Use this BEFORE sourcing, when your inputs are guesses -- it replaces a falsely
    precise single number with an honest range. The 'low'/'high' corners are the
    true envelope (see TonnageBand for why).
    """
    results = {
        level: calculate_order_tonnage(
            quantity,
            material_range.at(level),
            process_range.at(level),
            truck_capacity_t,
        )
        for level in ("low", "expected", "high")
    }
    return TonnageBand(low=results["low"], expected=results["expected"], high=results["high"])


# ---------------------------------------------------------------------------
# Demo: the FSS 0/32 position from the conversation
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # LV: Frostschutzschicht 0/32, 100 m3, abgerechnet nach Auftragsprofilen,
    # in nichttragfaehigen Teilflaechen (soft subgrade -> heavier loss).
    position = LayerQuantity(
        volume_m3=100.0,
        basis=VolumeBasis.COMPACTED_PROFILE,
        lv_position_ref="FSS 0/32 Verbreiterungsstreifen",
    )

    # --- Point estimate, using the KWN Sorte 21501 Proctordichte as the assumption ---
    material = MaterialProperties(
        proctor_density_t_m3=2.10,
        delivery_moisture=0.05,
        source="assumed ~ KWN Sortenverz. 2/22, Sorte 21501 (FSS 0/32 gebr.)",
    )
    process = ProcessAssumptions(degree_of_compaction=1.00, loss_factor=0.08)

    point = calculate_order_tonnage(position, material, process, truck_capacity_t=25.0)
    print("POINT ESTIMATE")
    print(f"  (material source: {material.source})")
    print(point)
    print()

    # --- Band: honest range while material is still unsourced ---
    material_band = MaterialPropertyRange(
        proctor_density_t_m3=ScalarRange(low=2.00, expected=2.10, high=2.25),
        delivery_moisture=ScalarRange(low=0.03, expected=0.05, high=0.07),
        source="assumed: gebr. Naturgestein FSS 0/32",
    )
    process_band = ProcessRange(
        degree_of_compaction=ScalarRange(low=0.98, expected=1.00, high=1.02),
        loss_factor=ScalarRange(low=0.05, expected=0.08, high=0.15),  # soft subgrade widens the top
    )

    band = calculate_order_tonnage_band(position, material_band, process_band, truck_capacity_t=25.0)
    print("BAND (pre-sourcing)")
    print(band)
