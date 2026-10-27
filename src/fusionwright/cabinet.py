"""Parametric rolling oak-slat cabinet, rebuilt from the hand sketch (sketch_spec in docs/examples/woodworking/SKETCH_SPEC.md).

What the sketch shows and this generator models:
  * 24" W x 24" H x 22.5" D, vertical oak slats on all four sides (10 across front/back, 6 per side)
  * a large circular scoop: the front (and, by default, back) slat tops follow one arc from the two top corners
    down to the centre height, so the slats are real arc-cut parts
  * a pair of hinged front doors across the middle three sections (the framed panel under the scoop in the 3/4
    view), two hinges per door on the outer edges, push-to-open (no visible pull), opening onto one large bay that
    holds a single pull-out drawer
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
    door_leaves: int = 2,
    door_span: str = "wide",
    drawer: bool = True,
    drawer_out: float = 0.0,
    drawer_depth: float = 18.0,
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
    if door_span not in ("wide", "centre"):
        raise ValueError("door_span must be 'wide' (doors and drawer across the centre and both step sections, the "
                         "default) or 'centre' (only the centre section).")
    if door_leaves not in (1, 2):
        raise ValueError("door_leaves must be 2 (a pair of doors, the default) or 1 (a single door hinged on the left).")
    if not 6.0 <= drawer_depth <= 20.0:
        raise ValueError("drawer_depth must be between 6 and 20 in (18 in matches standard full-extension slides).")
    if not 0.0 <= drawer_out <= drawer_depth - 2.0:
        raise ValueError(f"drawer_out must be between 0 and drawer_depth - 2 ({drawer_depth - 2:g}) in.")
    if drawer_out and not (door and door_open_deg >= 90.0):
        raise ValueError("The drawer is behind the doors: open them (door_open_deg of at least 90) before pulling the "
                         "drawer out.")

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
    wide = bool(door) and door_span == "wide"
    sec_a, sec_b = (1, 3) if wide else (2, 2)       # first / last section behind the doors
    x_lo, x_hi = x_edges[sec_a], x_edges[sec_b + 1]
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
                    door_leaves=door_leaves, door_span=door_span, drawer=drawer, drawer_out=drawer_out, drawer_depth=drawer_depth,
                    section_widths=[round(w, 4) for w in section_widths], scoop_radius=round(R, 4),
                    scoop_sag=sag),
    )
    add = p.boards.append

    def box_board(nm, group, mat, x, y, z, sx, sy, sz, grain="z", note=""):
        add(Board(nm, group, mat, x, y, z, sx, sy, sz, grain, None, None, note))

    door_open_box: dict[str, float] = {}

    # ---------------------------------------------------------------- plywood carcass (my proposal)
    box_board("Bottom panel", "bottom panel", PLY, skin_t, skin_t, base_z, inner_w, inner_d, ply_t, "x")
    if wide:                                        # one front wall across the centre and both step sections
        tops = [heights[i] - lid_t for i in range(5)]
        pts = [(x_edges[1], carcass_z), (x_edges[4], carcass_z), (x_edges[4], tops[3]), (x_edges[3], tops[3]),
               (x_edges[3], tops[2]), (x_edges[2], tops[2]), (x_edges[2], tops[1]), (x_edges[1], tops[1])]
        ops = [sh.prism("xz", sh.polygon(pts), y_front, y_front + ply_t)]
        ox0, ox1 = x_lo + 0.4, x_hi - 0.4
        oz0, oz1 = carcass_z + 0.5, tops[2] - 0.75
        ops.append(sh.box(ox0, y_front - 0.05, oz0, ox1 - ox0, ply_t + 0.1, oz1 - oz0, "cut"))
        door_open_box.update(x0=ox0, x1=ox1, z0=oz0, z1=oz1)
        for i in (1, 3):                            # the wedge finger openings stay on the step sections
            zt = tops[i] - 0.5
            xa, xb = x_edges[i] + 0.5, x_edges[i + 1] - 0.5
            wp = ([(xa, zt), (xb, zt), (xb, zt - 1.5), (xa, zt - 0.4)] if i == 1
                  else [(xa, zt), (xb, zt), (xb, zt - 0.4), (xa, zt - 1.5)])
            ops.append(sh.prism("xz", sh.polygon(wp), y_front - 0.05, y_front + ply_t + 0.05, "cut"))
        add(Board.from_shape("Front wall S2-S4", "front wall", PLY, ops, None, "x",
                             f"one panel across the three middle sections; {ox1 - ox0:.1f} in wide door opening for "
                             "the doors and drawer, wedge finger openings above"))
    for i in range(5):
        wall_top = heights[i] - lid_t
        for side, y0 in (("Front", y_front), ("Back", y_back - ply_t)):
            if wide and side == "Front" and i in (1, 2, 3):
                continue
            sx0, sw = x_edges[i], section_widths[i]
            ops = [sh.box(sx0, y0, carcass_z, sw, ply_t, wall_top - carcass_z)]
            note = ""
            if side == "Front" and i in (0, 4):                    # square opening under the tower lid
                s, cx = 1.75, sx0 + sw / 2
                top = wall_top - 0.9
                ops.append(sh.box(cx - s / 2, y0 - 0.05, top - s, s, ply_t + 0.1, s, "cut"))
                note = "1-3/4 in square finger opening"
            elif side == "Front" and i == 2 and door and not wide:  # access opening behind the front door
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
        if wide and k in (2, 3):                    # the drawer bay runs through the middle: no dividers inside it
            continue
        div_h = min(heights[k - 1], heights[k]) - lid_t - carcass_z
        box_board(f"Divider D{k}", "divider", PLY, x_edges[k] - ply_t / 2, y_front + ply_t, carcass_z, ply_t, wall_d,
                  div_h, "y")

    if wide:                                        # shelves over the drawer bay roof the step compartments
        bay_top = heights[2] - lid_t
        for nm, xa, xb in (("Bay shelf S2", x_edges[1] + ply_t / 2, x_edges[2]),
                           ("Bay shelf S4", x_edges[3], x_edges[4] - ply_t / 2)):
            box_board(nm, "shelf", PLY, xa, y_front + ply_t, bay_top - ply_t, xb - xa, wall_d, ply_t, "x",
                      "floor of the step compartment above, roof of the drawer bay")

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
    # front slats whose centre falls inside the door span form the door(s)
    door_js = [j for j in range(front_slats)
               if door and x_lo < j * pitch_x + sw_x / 2 < x_hi]
    if door and not door_js:
        raise ValueError("The door span is too narrow for a door: use fewer front_slats or a wider section.")
    if door and door_leaves == 2 and len(door_js) < 2:
        raise ValueError("Two doors need at least two slats in the door span: use more front_slats or door_leaves=1.")
    leaves: list[dict] = []                           # each leaf: slat indices, hinge edge, name, rotation
    if door_js:
        if door_leaves == 2:
            half_n = len(door_js) // 2
            groups = [(door_js[:half_n], "left", "L"), (door_js[half_n:], "right", "R")]
        else:
            groups = [(door_js, "left", "")]
        for js, hinge, tag in groups:
            lx0, lx1 = js[0] * pitch_x, js[-1] * pitch_x + sw_x
            rot = None
            if door_open_deg:                         # swing outward about the outer edge (right-hand about +Z)
                sign = -1.0 if hinge == "left" else 1.0
                rot = {"o": [lx0 if hinge == "left" else lx1, 0.0, 0.0], "ax": [0.0, 0.0, 1.0],
                       "deg": sign * float(door_open_deg)}
            leaves.append(dict(js=js, hinge=hinge, tag=tag, x0=lx0, x1=lx1, rot=rot))
    leaf_of = {j: lf for lf in leaves for j in lf["js"]}
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
            if side == "front" and j in leaf_of:
                lf = leaf_of[j]
                door_name = f"door {lf['tag']}".strip()
                rot, label = lf["rot"], f"Slat front {j + 1:02d} ({door_name})"
                note += f"; part of the front {door_name}"
            add(Board.from_shape(label, f"{side} slat", OAK, ops, rot, "z", note))
    if leaves:
        ox0, ox1 = door_open_box["x0"], door_open_box["x1"]
        zmid = (door_open_box["z0"] + door_open_box["z1"]) / 2
        for k, lf in enumerate(leaves):
            # battens sit inside the opening, behind this leaf's slats
            bx0 = ox0 + 0.05 if k == 0 else lf["x0"] + 0.05
            bx1 = ox1 - 0.05 if k == len(leaves) - 1 else lf["x1"] - 0.05
            suffix = f" {lf['tag']}" if lf["tag"] else ""
            for zc, nm in ((door_open_box["z0"] + 1.0, "low"), (door_open_box["z1"] - 1.0, "high")):
                add(Board.from_shape(f"Door{suffix} batten {nm}", "door batten", OAK,
                                     [sh.box(bx0, skin_t, zc - 0.75, bx1 - bx0, 0.5, 1.5)], lf["rot"], "x",
                                     "ties this door's slats together; fasten from the back"))
            if door_pull == "bar":                    # slim vertical oak pull on the free edge (adds 1/2 in of depth)
                bar_x = lf["x1"] - 1.0 if lf["hinge"] == "left" else lf["x0"] + 0.5
                add(Board.from_shape(f"Door{suffix} pull bar", "door pull", OAK,
                                     [sh.box(bar_x, -0.5, zmid - 3.0, 0.5, 0.5, 6.0)], lf["rot"], "z",
                                     "slim vertical grab bar, screwed from the back of the slats; adds 1/2 in to the depth"))
        n_l = len(leaves)
        p.hardware.append({"item": "Butt hinge 1-1/2 in (2 per door, on the outer edges)", "qty": 2 * n_l,
                           "for": "Front doors" if n_l == 2 else "Front door"})
        if door_pull == "bar":
            p.hardware.append({"item": "Magnetic catch (door)", "qty": n_l, "for": "Front doors"})
        else:                                         # push-to-open: no visible pull at all
            p.hardware.append({"item": "Push-to-open latch, magnetic, hidden behind the door (1 per door)",
                               "qty": n_l, "for": "Front doors" if n_l == 2 else "Front door"})

    # ---------------------------------------------------------------- pull-out drawer behind the doors
    if door_js and drawer:
        t_d = 0.5                                                     # drawer sides / front / back (solid oak)
        cx_c = (x_lo + x_hi) / 2
        dw = (x_hi - x_lo - ply_t) - 1.0                              # 1/2 in each side for the slides
        # doors standing open at 90 deg reach 1 in in front of their hinge edge: keep the drawer clear of them
        reach = 1.0 + 0.05
        left_lim = next((lf["x0"] + reach for lf in leaves if lf["hinge"] == "left"), x_lo)
        right_lim = next((lf["x1"] - reach for lf in leaves if lf["hinge"] == "right"), x_hi)
        half_w = min(dw / 2, cx_c - left_lim, right_lim - cx_c)
        dw = 2 * half_w
        dx0 = cx_c - dw / 2
        dz0 = door_open_box["z0"] + 0.25
        dh = (door_open_box["z1"] - door_open_box["z0"]) - 0.5
        dy0 = y_front + ply_t - drawer_out                            # front of the drawer, just behind the front wall
        if dw > door_open_box["x1"] - door_open_box["x0"] - 0.25:
            raise ValueError("The drawer would not fit through the door opening: widen the sections behind the doors.")
        front_ops = [sh.box(dx0, dy0, dz0, dw, t_d, dh),
                     sh.box(cx_c - 2.0, dy0 - 0.05, dz0 + dh - 0.75, 4.0, 0.3, 0.8, "cut")]    # finger notch, top edge
        add(Board.from_shape("Drawer front", "drawer", OAK, front_ops, None, "x",
                             "hidden behind the doors; 4 in finger notch in the top edge instead of a handle"))
        box_board("Drawer back", "drawer", OAK, dx0, dy0 + drawer_depth - t_d, dz0, dw, t_d, dh, "x")
        for sd, xs in (("left", dx0), ("right", dx0 + dw - t_d)):
            box_board(f"Drawer side {sd}", "drawer", OAK, xs, dy0 + t_d, dz0, t_d, drawer_depth - 2 * t_d, dh, "y")
        box_board("Drawer bottom", "drawer", PLY, dx0 + t_d, dy0 + t_d, dz0, dw - 2 * t_d, drawer_depth - 2 * t_d, 0.25,
                  "y", "1/4 in plywood, glued into a rabbet or groove in the four drawer walls")
        p.hardware.append({"item": f"Full-extension ball-bearing drawer slides, {drawer_depth:g} in (pair)", "qty": 1,
                           "for": "Drawer"})
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
        "Front doors: the framed panel under the scoop in the 3/4 view is a pair of doors with two hinges per door on "
        "the outer edges, push-to-open so nothing shows on the front. With door_span='wide' (default) they span the "
        "centre and both step sections, so the doors open onto one big bay holding a single pull-out drawer on 18 in "
        "full-extension slides, and the step lids open onto compartments above the bay. door_span='centre' keeps the "
        "doors and drawer to the centre section only; door_leaves=1 gives a single door, door=False none, "
        "drawer=False an empty bay; door_open_deg=90 and drawer_out=12 show it open.",
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
