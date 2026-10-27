"""Parametric rolling oak-slat cabinet, rebuilt from the hand sketch (sketch_spec in docs/SKETCH_SPEC.md).

What the sketch shows and this generator models:
  * 24" W x 24" H x 22.5" D, vertical oak slats on all four sides (10 across front/back, 6 per side)
  * a large circular scoop: the front (and, by default, back) slat tops follow one arc from the two top corners
    down to the centre height, so the slats are real arc-cut parts
  * a hinged front door in the middle section (the framed panel under the scoop in the 3/4 view): the four centre
    slats on two oak battens, hinged on the left, push-to-open (no visible pull), opening onto the centre compartment
  * five hinged lids/doors side by side at three heights: towers 24", steps 19", centre 14"
  * stepped plywood carcass behind the slats; the carcass boxes stand proud of the arc; dark square openings on the
    tower fronts and dark wedge openings on the step fronts act as the finger pulls
  * slat panel stops above the floor on an apron; four L-shaped corner feet each hide a swivel caster, the caster
    plate screwed under a top plate (the inset drawing)
What the sketch does NOT show (interior, hinges, exact pull shapes) is my engineering proposal and is listed in
`notes`.
"""
from __future__ import annotations

import math

from . import shapes as sh
from .model import Board, Project, SHEET, SOLID

OAK, PLY, STEEL, RUBBER = "oak", "ply", "steel", "rubber"


def _slats(length: float, n: int, gap: float) -> tuple[float, float]:
    w = (length - (n - 1) * gap) / n
    return w, w + gap


def build_cabinet(
    width: float = 24.0,
    depth: float = 22.5,
    tower_h: float = 24.0,
    step_h: float = 19.0,
    center_h: float = 14.0,
    skin_t: float = 0.5,
    front_slats: int = 10,
    side_slats: int = 6,
    slat_gap: float = 0.15,
    ply_t: float = 0.75,
    lid_t: float = 0.75,
    base_z: float = 3.25,
    caster_h: float = 2.5,
    plate_t: float = 0.75,
    foot_arm: float = 4.5,
    foot_t: float = 1.25,
    foot_clear: float = 0.3,
    apron_z: float = 1.4,
    section_widths: list[float] | None = None,
    arc_on_back: bool = True,
    open_deg: float = 0.0,
    open_sections: tuple[int, ...] = (0, 1, 3, 4),
    door: bool = True,
    door_open_deg: float = 0.0,
    door_pull: str = "push",
    name: str = "Rolling oak slat cabinet",
) -> Project:
    inner_w = width - 2 * skin_t
    inner_d = depth - 2 * skin_t
    if section_widths is None:
        ratios = [4.0, 3.75, 7.5, 3.75, 4.0]
        section_widths = [r / sum(ratios) * inner_w for r in ratios]
    if len(section_widths) != 5:
        raise ValueError("section_widths needs 5 numbers: tower, step, centre, step, tower.")
    if abs(sum(section_widths) - inner_w) > 1e-3:
        raise ValueError(f"section_widths add up to {sum(section_widths):.3f} in but the interior is {inner_w:.3f} in "
                         f"(width {width} minus 2 x skin {skin_t}). Adjust them or omit section_widths.")
    if not (tower_h >= step_h >= center_h > base_z + ply_t + lid_t):
        raise ValueError("Heights must satisfy tower_h >= step_h >= center_h > base_z + ply_t + lid_t.")
    if tower_h <= center_h:
        raise ValueError("tower_h must be taller than center_h so the scoop has a depth.")
    if base_z - plate_t - caster_h < -1e-9:
        raise ValueError(f"base_z ({base_z}) is too low: it must be at least plate_t + caster_h "
                         f"({plate_t + caster_h}) so the casters fit under the foot plates.")
    cs = 3.0                                   # caster swivel centre, inset from both outer faces of a corner
    if foot_arm < cs + 1.0:
        raise ValueError(f"foot_arm must be at least {cs + 1.0} in so the L walls hide the caster.")
    if not 1 <= front_slats <= 40 or not 1 <= side_slats <= 40:
        raise ValueError("front_slats and side_slats must be between 1 and 40.")
    if door_pull not in ("push", "bar"):
        raise ValueError("door_pull must be 'push' (push-to-open, nothing visible) or 'bar' (slim vertical pull).")
    if not 0.0 <= door_open_deg <= 120.0:
        raise ValueError("door_open_deg must be between 0 and 120 degrees (0 = closed).")

    # scoop arc through the two top corners, lowest at the centre
    half, sag = width / 2, tower_h - center_h
    R = (half**2 + sag**2) / (2 * sag)
    zc = center_h + R

    def arc_z(x: float) -> float:
        return zc - math.sqrt(max(R * R - (x - half) ** 2, 0.0))

    heights = [tower_h, step_h, center_h, step_h, tower_h]
    labels = ["S1 tower", "S2 step", "S3 centre", "S4 step", "S5 tower"]
    x_edges = [skin_t]
    for w in section_widths:
        x_edges.append(x_edges[-1] + w)
    y_front, y_back = skin_t, depth - skin_t        # inside faces of the front / back skin
    carcass_z = base_z + ply_t

    p = Project(
        name=name,
        materials={
            OAK: {"label": "White oak (solid)", "kind": SOLID, "color": "#c8a46a"},
            PLY: {"label": "Birch plywood", "kind": SHEET, "color": "#e6d3a8"},
            STEEL: {"label": "Caster steel", "kind": "hardware", "color": "#8a8f94"},
            RUBBER: {"label": "Caster rubber", "kind": "hardware", "color": "#26262a"},
        },
        params=dict(width=width, depth=depth, tower_h=tower_h, step_h=step_h, center_h=center_h, skin_t=skin_t,
                    front_slats=front_slats, side_slats=side_slats, slat_gap=slat_gap, ply_t=ply_t, lid_t=lid_t,
                    base_z=base_z, caster_h=caster_h, plate_t=plate_t, foot_arm=foot_arm, foot_t=foot_t,
                    foot_clear=foot_clear, apron_z=apron_z, arc_on_back=arc_on_back, open_deg=open_deg, door=door,
                    door_open_deg=door_open_deg, door_pull=door_pull,
                    section_widths=[round(w, 4) for w in section_widths], scoop_radius=round(R, 4),
                    scoop_sag=sag),
    )
    add = p.boards.append

    def box_board(nm, group, mat, x, y, z, sx, sy, sz, grain="z", note=""):
        add(Board(nm, group, mat, x, y, z, sx, sy, sz, grain, None, None, note))

    door_open_box: dict[str, float] = {}

    # ---------------------------------------------------------------- plywood carcass (my proposal)
    box_board("Bottom panel", "bottom panel", PLY, skin_t, skin_t, base_z, inner_w, inner_d, ply_t, "x")
    for i in range(5):
        wall_top = heights[i] - lid_t
        for side, y0 in (("Front", y_front), ("Back", y_back - ply_t)):
            sx0, sw = x_edges[i], section_widths[i]
            ops = [sh.box(sx0, y0, carcass_z, sw, ply_t, wall_top - carcass_z)]
            note = ""
            if side == "Front" and i in (0, 4):                    # square opening under the tower lid
                s, cx = 1.75, sx0 + sw / 2
                top = wall_top - 0.9
                ops.append(sh.box(cx - s / 2, y0 - 0.05, top - s, s, ply_t + 0.1, s, "cut"))
                note = "1-3/4 in square finger opening"
            elif side == "Front" and i == 2 and door:              # access opening behind the front door
                ox0, ox1 = sx0 + 0.4, sx0 + sw - 0.4
                oz0, oz1 = carcass_z + 0.5, wall_top - 0.75
                ops.append(sh.box(ox0, y0 - 0.05, oz0, ox1 - ox0, ply_t + 0.1, oz1 - oz0, "cut"))
                note = "door opening, 6-3/4 in wide"
                door_open_box.update(x0=ox0, x1=ox1, z0=oz0, z1=oz1)
            elif side == "Front" and i in (1, 3):                  # wedge opening on the step boxes
                m, zt = 0.5, wall_top - 0.5
                xa, xb = sx0 + m, sx0 + sw - m
                pts = ([(xa, zt), (xb, zt), (xb, zt - 1.5), (xa, zt - 0.4)] if i == 1
                       else [(xa, zt), (xb, zt), (xb, zt - 0.4), (xa, zt - 1.5)])
                ops.append(sh.prism("xz", sh.polygon(pts), y0 - 0.05, y0 + ply_t + 0.05, "cut"))
                note = "wedge-shaped finger opening"
            add(Board.from_shape(f"{side} wall {labels[i][:2]}", f"{side.lower()} wall", PLY, ops, None, "x", note))
    wall_d = inner_d - 2 * ply_t
    end_h = tower_h - lid_t - carcass_z
    box_board("End wall left", "end wall", PLY, skin_t, y_front + ply_t, carcass_z, ply_t, wall_d, end_h, "y")
    box_board("End wall right", "end wall", PLY, width - skin_t - ply_t, y_front + ply_t, carcass_z, ply_t, wall_d,
              end_h, "y")
    for k in range(1, 5):
        div_h = min(heights[k - 1], heights[k]) - lid_t - carcass_z
        box_board(f"Divider D{k}", "divider", PLY, x_edges[k] - ply_t / 2, y_front + ply_t, carcass_z, ply_t, wall_d,
                  div_h, "y")

    # ---------------------------------------------------------------- hinged lids / doors (hinged at the back)
    for i in range(5):
        z0 = heights[i] - lid_t
        ops = [sh.box(x_edges[i], skin_t, z0, section_widths[i], inner_d, lid_t)]
        note = "hinged at back"
        if i == 2:                                                 # centre lid has no side box: add a finger notch
            ops.append(sh.cyl("z", (x_edges[i] + section_widths[i] / 2, skin_t, z0 + lid_t / 2), 0.7, lid_t + 0.2, "cut"))
            note += "; half-round finger notch added (not in sketch)"
        rot = None
        if open_deg and i in open_sections:
            rot = {"o": [0.0, y_back, z0], "ax": [-1.0, 0.0, 0.0], "deg": float(open_deg)}
            note += f"; shown open {open_deg:g} deg"
        add(Board.from_shape(f"Lid {labels[i][:2]}", "lid", OAK, ops, rot, "y", note))
        p.hardware.append({"item": "Butt hinge 2 in", "qty": 2, "for": f"Lid {labels[i][:2]}"})

    # ---------------------------------------------------------------- vertical oak slats, four sides
    sw_x, pitch_x = _slats(width, front_slats, slat_gap)
    # front slats whose centre falls inside the centre section form the door
    door_js = [j for j in range(front_slats)
               if door and x_edges[2] < j * pitch_x + sw_x / 2 < x_edges[3]]
    if door and not door_js:
        raise ValueError("The centre section is too narrow for a door: use fewer front_slats or a wider section.")
    door_x0 = door_js[0] * pitch_x if door_js else 0.0
    door_x1 = door_js[-1] * pitch_x + sw_x if door_js else 0.0
    door_rot = None
    if door_js and door_open_deg:                     # swing outward about the front-left corner (right-hand about +Z)
        door_rot = {"o": [door_x0, 0.0, 0.0], "ax": [0.0, 0.0, 1.0], "deg": -float(door_open_deg)}
    for side, ya, yb, arc in (("front", 0.0, skin_t, True), ("back", depth - skin_t, depth, arc_on_back)):
        for j in range(front_slats):
            x0 = j * pitch_x
            x1 = x0 + sw_x
            xm = (x0 + x1) / 2
            if arc:
                path = [["m", x0, base_z], ["l", x1, base_z], ["l", x1, arc_z(x1)],
                        ["a", xm, arc_z(xm), x0, arc_z(x0)]]
                note = "top cut to the scoop arc"
            else:
                path = sh.polygon([(x0, base_z), (x1, base_z), (x1, tower_h), (x0, tower_h)])
                note = ""
            ops = [sh.prism("xz", path, ya, yb)]
            rot, label = None, f"Slat {side} {j + 1:02d}"
            if side == "front" and j in door_js:
                rot, label = door_rot, f"Slat front {j + 1:02d} (door)"
                note += "; part of the front door"
            add(Board.from_shape(label, f"{side} slat", OAK, ops, rot, "z", note))
    if door_js:
        bx0, bx1 = door_open_box["x0"] + 0.05, door_open_box["x1"] - 0.05      # battens sit inside the opening
        for k, (zc, nm) in enumerate(((door_open_box["z0"] + 1.0, "low"), (door_open_box["z1"] - 1.0, "high"))):
            add(Board.from_shape(f"Door batten {nm}", "door batten", OAK,
                                 [sh.box(bx0, skin_t, zc - 0.75, bx1 - bx0, 0.5, 1.5)], door_rot, "x",
                                 "ties the four door slats together; fasten from the back"))
        p.hardware.append({"item": "Butt hinge 1-1/2 in (door, on the left edge)", "qty": 2, "for": "Front door"})
        if door_pull == "bar":                        # slim vertical oak pull on the free edge (adds 1/2 in of depth)
            zc = (door_open_box["z0"] + door_open_box["z1"]) / 2
            add(Board.from_shape("Door pull bar", "door pull", OAK,
                                 [sh.box(door_x1 - 1.0, -0.5, zc - 3.0, 0.5, 0.5, 6.0)], door_rot, "z",
                                 "slim vertical grab bar, screwed from the back of the slats; adds 1/2 in to the depth"))
            p.hardware.append({"item": "Magnetic catch (door)", "qty": 1, "for": "Front door"})
        else:                                         # push-to-open: no visible pull at all
            p.hardware.append({"item": "Push-to-open latch, magnetic, hidden behind the door (door)", "qty": 1,
                               "for": "Front door"})
    sw_y, pitch_y = _slats(inner_d, side_slats, slat_gap)
    for side, xa in (("left", 0.0), ("right", width - skin_t)):
        for j in range(side_slats):
            box_board(f"Slat {side} {j + 1:02d}", f"{side} slat", OAK, xa, y_front + j * pitch_y, base_z, skin_t, sw_y,
                      tower_h - base_z)

    # ---------------------------------------------------------------- apron between the feet (hides the base)
    ap_h = base_z - apron_z
    box_board("Apron front", "apron", OAK, foot_arm, 0.0, apron_z, width - 2 * foot_arm, skin_t, ap_h, "x")
    box_board("Apron back", "apron", OAK, foot_arm, depth - skin_t, apron_z, width - 2 * foot_arm, skin_t, ap_h, "x")
    box_board("Apron left", "apron", OAK, 0.0, foot_arm, apron_z, skin_t, depth - 2 * foot_arm, ap_h, "y")
    box_board("Apron right", "apron", OAK, width - skin_t, foot_arm, apron_z, skin_t, depth - 2 * foot_arm, ap_h, "y")

    # ---------------------------------------------------------------- L-shaped corner feet hiding the casters
    plate_z = base_z - plate_t
    wall_h = plate_z - foot_clear
    for cname, fx, fy in (("FL", 0, 0), ("FR", 1, 0), ("BL", 0, 1), ("BR", 1, 1)):
        def mx(x0, sx):                                           # mirror a box extent about the cabinet centre
            return width - x0 - sx if fx else x0

        def my(y0, sy):
            return depth - y0 - sy if fy else y0
        box_board(f"Foot {cname} wall A", "foot", OAK, mx(0, foot_arm), my(0, foot_t), foot_clear, foot_arm, foot_t,
                  wall_h, "x")
        box_board(f"Foot {cname} wall B", "foot", OAK, mx(0, foot_t), my(foot_t, foot_arm - foot_t), foot_clear,
                  foot_t, foot_arm - foot_t, wall_h, "y")
        box_board(f"Foot {cname} top plate", "foot", OAK, mx(0, foot_arm), my(0, foot_arm), plate_z, foot_arm, foot_arm,
                  plate_t, "x")
        # caster: plate, swivel, two fork plates, wheel with axle
        cx = width - cs if fx else cs
        cy = depth - cs if fy else cs
        plate_h, swivel_h = 0.1, 0.3
        z_plate = plate_z - plate_h
        wheel_r = (caster_h - plate_h - swivel_h - 0.3) / 2
        box_board(f"Caster {cname} plate", "caster", STEEL, cx - 1.0, cy - 1.25, z_plate, 2.0, 2.5, plate_h, "x")
        add(Board.from_shape(f"Caster {cname} swivel", "caster", STEEL,
                             [sh.cyl("z", (cx, cy, z_plate - swivel_h / 2), 0.85, swivel_h)]))
        z_fork_top = z_plate - swivel_h
        for side, off in (("a", -0.5), ("b", 0.4)):          # fork plates touch the wheel faces
            box_board(f"Caster {cname} fork {side}", "caster", STEEL, cx + off, cy - 0.6, 0.4, 0.1, 1.2,
                      z_fork_top - 0.4)
        wz = wheel_r                                              # wheel sits on the floor (z = 0)
        add(Board.from_shape(f"Caster {cname} wheel", "caster", RUBBER,
                             [sh.cyl("x", (cx, cy, wz), wheel_r, 0.8)]))
    p.hardware.append({"item": f"Swivel caster, {caster_h} in overall height (2 locking)", "qty": 4, "for": "feet"})

    p.notes += [
        "Front door: the framed panel under the scoop in the 3/4 view is read as an access door to the centre compartment "
        "(four slats on two battens, hinged on the left, push-to-open so nothing shows on the front). The other compartments open through their lids. "
        "Set door=False for no door, door_open_deg=90 to show it open.",
        "Read from the sketch: arc-cut slat tops, five lids at 24/19/14 in, stepped boxes, L-shaped corner feet hiding "
        "four casters (plate screwed under a top plate), slats stopping above the floor on an apron.",
        "Interpretations to confirm with the designer: the dark squares (tower fronts) and dark wedges (step fronts) "
        "are modelled as finger openings through the plywood front wall; the tilted blocks in the 3/4 view are the "
        "lids shown open (use open_deg); the scoop is cut in both the front and the back skin (arc_on_back).",
        "My proposal, not in the sketch: plywood carcass, dividers, lid hinges at the back, centre-lid finger notch, "
        "apron height, caster size.",
        "Slats are butt-fastened to the plywood carcass; use glue plus brad nails or screws from the inside.",
    ]
    return p
