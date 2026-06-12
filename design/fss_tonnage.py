"""
FSS 0/32 base-layer calculator for the pool project.

Two pieces:
  1. elongated_octagon_area() — area of a rectangle with chamfered corners
     (your wood-edge footprint).
  2. fss_tonnage() — tonnes of compacted FSS 0/32 to order for a layer.

Density convention: mass is conserved between loose and compacted states,
so to order by weight you take the COMPACTED (in-place) volume times the
COMPACTED density. For TL SoB-StB FSS 0/32 that's ~2.0 t/m3 (use the
supplier's stated Einbaudichte if they give one).
"""

import math


def elongated_octagon_area(long_side, short_end, chamfer, angle_deg=48.0):
    """
    Area of an elongated octagon = rectangle with four equal corners chamfered.
    All lengths in the same unit; returns that unit squared.

    long_side : straight top/bottom edge (e.g. 400 cm)
    short_end : straight left/right edge (e.g. 185 cm)
    chamfer   : chamfer hypotenuse, one corner cut (e.g. 150 cm)
    angle_deg : angle between chamfer and the long side (e.g. 48)
    """
    a = chamfer * math.cos(math.radians(angle_deg))   # leg along long side
    b = chamfer * math.sin(math.radians(angle_deg))   # leg along short end
    bounding = (long_side + 2 * a) * (short_end + 2 * b)
    corners = 2 * a * b                               # four half-triangles
    return bounding - corners


def inset_area(outer_area, perimeter, edge_width):
    """
    Approximate inner fill area when a retaining edge of `edge_width` rings the
    perimeter. Boards on edge -> ~4 cm; boards laid flat -> ~20 cm.
    Good enough for a thin inset; same units as outer_area / perimeter.
    """
    return outer_area - perimeter * edge_width


def fss_tonnage(area_m2, depth_cm, density_t_per_m3=2.0, waste=0.10):
    """
    Tonnes of FSS 0/32 to order for a compacted layer.

    density_t_per_m3 : ~2.0 compacted FSS 0/32 (override with supplier value)
    waste            : fractional margin for spillage / uneven subgrade
    Returns a dict with the compacted volume and net / order tonnages.
    """
    volume_m3 = area_m2 * (depth_cm / 100.0)
    tonnes = volume_m3 * density_t_per_m3
    return {
        "compacted_m3": round(volume_m3, 3),
        "tonnes_net": round(tonnes, 2),
        "tonnes_order": round(tonnes * (1 + waste), 2),
    }


if __name__ == "__main__":
    # Your elongated octagon (cm)
    L, S, C, ANG = 400, 185, 150, 48
    outer_cm2 = elongated_octagon_area(L, S, C, ANG)
    perimeter_cm = 2 * L + 2 * S + 4 * C            # 1770 cm

    scenarios = {
        "outer footprint":            outer_cm2,
        "inner (boards on edge, 4cm)": inset_area(outer_cm2, perimeter_cm, 4),
        "inner (boards flat, 20cm)":   inset_area(outer_cm2, perimeter_cm, 20),
    }

    print(f"perimeter = {perimeter_cm/100:.2f} m\n")
    print(f"{'scenario':28s} {'area m2':>8s} {'vol m3':>7s} {'order t':>8s}")
    for label, cm2 in scenarios.items():
        area_m2 = cm2 / 10_000
        r = fss_tonnage(area_m2, depth_cm=8)          # change depth here
        print(f"{label:28s} {area_m2:8.1f} {r['compacted_m3']:7.2f} "
              f"{r['tonnes_order']:8.1f}")
