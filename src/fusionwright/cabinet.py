"""Parametric slatted rolling cabinet (stepped top, hinged lids, caster blocks).

This is the flagship example. All dimensions are parameters; defaults reproduce the
hand-sketched 24" x 24" x 22.5" oak cabinet. Two details of the sketch were never confirmed
(the dark wedges where the curve meets each tower, and the tilted blocks on top of the towers),
so they are deliberately NOT modelled; see `notes` on the returned project.
"""
from __future__ import annotations

from .model import Board, Project, SHEET, SOLID

OAK = "oak"
PLY = "ply"


def _fit_slats(length: float, target_w: float, gap: float) -> tuple[int, float]:
    """How many slats of ~target_w with `gap` between them fill `length` exactly."""
    n = max(1, round((length + gap) / (target_w + gap)))
    w = (length - (n - 1) * gap) / n
    return n, w


def build_cabinet(
    width: float = 24.0,
    depth: float = 22.5,
    tower_h: float = 24.0,
    step_h: float = 19.0,
    center_h: float = 14.0,
    slat_w: float = 1.5,
    slat_t: float = 0.75,
    slat_gap: float = 0.5,
    ply_t: float = 0.75,
    lid_t: float = 0.75,
    base_z: float = 3.0,
    block_leg: float = 3.0,
    block_t: float = 1.5,
    caster_h: float = 2.5,
    section_widths: list[float] | None = None,
    name: str = "Rolling oak slat cabinet",
) -> Project:
    inner_w = width - 2 * slat_t
    inner_d = depth - 2 * slat_t
    if section_widths is None:
        ratios = [4.5, 5.0, 3.5, 5.0, 4.5]
        s = sum(ratios)
        section_widths = [r / s * inner_w for r in ratios]
    if len(section_widths) != 5:
        raise ValueError("section_widths needs 5 numbers: tower, step, center, step, tower.")
    if abs(sum(section_widths) - inner_w) > 1e-3:
        raise ValueError(
            f"section_widths add up to {sum(section_widths):.3f} in but the interior is {inner_w:.3f} in "
            f"(width {width} minus 2 x slat thickness {slat_t}). Adjust them or omit section_widths."
        )
    if not (tower_h >= step_h >= center_h > base_z + ply_t + lid_t):
        raise ValueError("Heights must satisfy tower_h >= step_h >= center_h > base_z + ply_t + lid_t.")
    if block_leg < caster_h or base_z < caster_h:
        raise ValueError("base_z (and block_leg) must be at least caster_h so the blocks can hide the casters.")

    heights = [tower_h, step_h, center_h, step_h, tower_h]
    labels = ["S1 tower", "S2 step", "S3 center", "S4 step", "S5 tower"]
    x_edges = [slat_t]
    for w in section_widths:
        x_edges.append(x_edges[-1] + w)

    def height_at(x: float) -> float:
        for i in range(5):
            if x < x_edges[i + 1] or i == 4:
                return heights[i]
        return heights[-1]

    p = Project(
        name=name,
        materials={
            OAK: {"label": "White oak (solid)", "kind": SOLID, "color": "#c8a46a"},
            PLY: {"label": "Birch plywood", "kind": SHEET, "color": "#e6d3a8"},
        },
        params=dict(width=width, depth=depth, tower_h=tower_h, step_h=step_h, center_h=center_h,
                    slat_w=slat_w, slat_t=slat_t, slat_gap=slat_gap, ply_t=ply_t, lid_t=lid_t,
                    base_z=base_z, block_leg=block_leg, block_t=block_t, caster_h=caster_h,
                    section_widths=[round(w, 4) for w in section_widths]),
    )
    add = p.boards.append
    carcass_z = base_z + ply_t
    wall_d = inner_d - 2 * ply_t

    # --- plywood carcass ----------------------------------------------------------------
    add(Board("Bottom panel", "bottom panel", PLY, slat_t, slat_t, base_z, inner_w, inner_d, ply_t, "x"))
    for i in range(5):
        wall_h = heights[i] - lid_t - carcass_z
        add(Board(f"Front wall {labels[i][:2]}", "front wall", PLY, x_edges[i], slat_t, carcass_z,
                  section_widths[i], ply_t, wall_h, "x"))
        add(Board(f"Back wall {labels[i][:2]}", "back wall", PLY, x_edges[i], depth - slat_t - ply_t, carcass_z,
                  section_widths[i], ply_t, wall_h, "x"))
    end_h = tower_h - lid_t - carcass_z
    add(Board("End wall left", "end wall", PLY, slat_t, slat_t + ply_t, carcass_z, ply_t, wall_d, end_h, "y"))
    add(Board("End wall right", "end wall", PLY, width - slat_t - ply_t, slat_t + ply_t, carcass_z,
              ply_t, wall_d, end_h, "y"))
    for k in range(1, 5):
        div_h = min(heights[k - 1], heights[k]) - lid_t - carcass_z
        add(Board(f"Divider D{k}", "divider", PLY, x_edges[k] - ply_t / 2, slat_t + ply_t, carcass_z,
                  ply_t, wall_d, div_h, "y"))

    # --- hinged lids (oak) --------------------------------------------------------------
    for i in range(5):
        add(Board(f"Lid {labels[i][:2]}", "lid", OAK, x_edges[i], slat_t, heights[i] - lid_t,
                  section_widths[i], inner_d, lid_t, "y"))
        p.features.append({"type": "finger_pull", "board": f"Lid {labels[i][:2]}", "dia": 1.25,
                           "center": [round(x_edges[i] + section_widths[i] / 2, 4), slat_t]})
        p.hardware.append({"item": "Butt hinge 2 in", "qty": 2, "for": f"Lid {labels[i][:2]}"})

    # --- vertical oak slats on all four sides -------------------------------------------
    n_x, sw_x = _fit_slats(width, slat_w, slat_gap)
    for side, y0 in (("front", 0.0), ("back", depth - slat_t)):
        for j in range(n_x):
            x0 = j * (sw_x + slat_gap)
            h = height_at(x0 + sw_x / 2)
            add(Board(f"Slat {side} {j + 1:02d}", f"{side} slat", OAK, x0, y0, base_z, sw_x, slat_t, h - base_z, "z"))
    n_y, sw_y = _fit_slats(inner_d, slat_w, slat_gap)
    for side, x0 in (("left", 0.0), ("right", width - slat_t)):
        for j in range(n_y):
            y0 = slat_t + j * (sw_y + slat_gap)
            add(Board(f"Slat {side} {j + 1:02d}", f"{side} slat", OAK, x0, y0, base_z, slat_t, sw_y,
                      tower_h - base_z, "z"))

    # --- L-shaped corner blocks hiding the casters --------------------------------------
    for cname, fx, fy in (("FL", 0, 0), ("FR", 1, 0), ("BL", 0, 1), ("BR", 1, 1)):
        xa = width - block_leg if fx else 0.0
        ya = depth - block_t if fy else 0.0
        add(Board(f"Caster block {cname} a", "caster block", OAK, xa, ya, 0.0, block_leg, block_t, base_z, "x"))
        xb = width - block_t if fx else 0.0
        yb = depth - block_leg if fy else block_t
        add(Board(f"Caster block {cname} b", "caster block", OAK, xb, yb, 0.0, block_t, block_leg - block_t, base_z, "y"))
    p.hardware.append({"item": f"Swivel caster, {caster_h} in overall height (2 locking)", "qty": 4, "for": "base"})

    p.notes += [
        "Dark wedges at the tower/curve joints and tilted blocks on the tower tops are NOT modelled "
        "(unconfirmed from the sketch).",
        "Slats are butt-fastened to the plywood carcass; choose glue + brad nails or screws from the inside.",
        "Finger pulls are 1-1/4 in half-round notches on the front edge of each lid.",
    ]
    return p
