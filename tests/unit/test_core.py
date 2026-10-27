import math, re
from fusionwright.cabinet import build_cabinet
from fusionwright.cutlist import cutlist, board_feet, to_markdown, to_csv
from fusionwright.nesting import nest_sheets, nest_sheets_svg, cut_lumber
from fusionwright.drawings import three_view_svg
from fusionwright.meshout import to_stl, to_obj, mesh_volume, skipped_cuts, triangulate
from fusionwright import shapes as sh
from fusionwright.model import Project, frac
import pytest


def test_overall_size_matches_sketch():
    p = build_cabinet()
    w, d, h = p.overall()
    assert (round(w, 3), round(d, 3), round(h, 3)) == (24.0, 22.5, 24.0)


def test_no_board_overlaps():
    p = build_cabinet()
    assert p.interferences() == [], p.interferences()[:5]


def test_three_stepped_heights():
    p = build_cabinet()
    tops = sorted({round(b.z + b.sz, 3) for b in p.boards if b.group == "lid"}, reverse=True)
    assert tops == [24.0, 19.0, 14.0]


def test_sketch_details_are_present():
    """Everything read from the hand sketch is modelled, not just boxes."""
    p = build_cabinet()
    names = [b.name for b in p.boards]
    assert sum(n.startswith("Slat front") for n in names) == 10 and sum(n.startswith("Slat back") for n in names) == 10
    assert sum(n.startswith("Slat left") for n in names) == 6 and sum(n.startswith("Slat right") for n in names) == 6
    assert sum(n.startswith("Lid ") for n in names) == 5
    # arc-cut slats: the shape contains a real arc segment and the heights fall from the corners to the centre
    arcs = [b for b in p.boards if b.group == "front slat"]
    assert all(any(seg[0] == "a" for seg in b.shape[0]["path"]) for b in arcs)
    tops = [b.z + b.sz for b in arcs]
    assert tops[0] > tops[len(tops) // 2] and tops[-1] > tops[len(tops) // 2]
    # four L-shaped corner feet (two walls + top plate each) hiding four casters (plate, swivel, 2 forks, wheel)
    assert sum("wall A" in n for n in names) == 4 and sum("wall B" in n for n in names) == 4
    assert sum(n.endswith("wheel") for n in names) == 4 and sum(n.endswith("top plate") for n in names) == 4
    # wedge and square openings are cuts through the plywood fronts
    cuts = [b for b in p.boards if b.shape and any(o["op"] == "cut" for o in b.shape)]
    assert len(cuts) >= 3


def test_front_doors_open_onto_the_centre_compartment_with_a_drawer():
    p = build_cabinet()
    doors = [b for b in p.boards if "(door" in b.name]
    assert len(doors) == 8 and sum(b.name.startswith("Door") and "batten" in b.name for b in p.boards) == 4
    assert {b.name.split("(")[1] for b in doors} == {"door L)", "door R)"}          # two leaves, four slats each
    wall = next(b for b in p.boards if b.name == "Front wall S1-S5")      # one panel across the whole front
    assert any(o["op"] == "cut" for o in wall.shape)                     # the opening the doors cover
    assert not any(b.name in ("Divider D2", "Divider D3") for b in p.boards)       # the bay runs through the middle
    assert {b.name for b in p.boards if b.group == "shelf"} == {"Bay shelf left", "Bay shelf right"}
    narrow = build_cabinet(door_span="centre")
    assert len([b for b in build_cabinet(door_span="wide").boards if "(door" in b.name]) == 6
    assert len([b for b in narrow.boards if "(door" in b.name]) == 4 and any(b.name == "Divider D2" for b in narrow.boards)
    assert next(b for b in p.boards if b.name == "Drawer front").sx > 3 * next(b for b in narrow.boards if b.name == "Drawer front").sx / 1.5
    hinge = next(h for h in p.hardware if "Butt hinge 1-1/2" in h["item"])
    assert hinge["qty"] == 4                                             # two hinges on each door
    assert any("Push-to-open" in h["item"] and h["qty"] == 2 for h in p.hardware)    # nothing visible on the front
    assert not any(o["k"] == "cyl" and o["op"] == "cut" for b in doors for o in b.shape)    # no hole, no pull
    drawer = [b for b in p.boards if b.group == "drawer"]
    assert {b.name for b in drawer} == {"Drawer front", "Drawer back", "Drawer side left", "Drawer side right",
                                        "Drawer bottom"}
    assert any("drawer slides" in h["item"] for h in p.hardware)
    opening = wall
    assert all(b.y >= opening.y + opening.sy - 1e-9 for b in drawer)     # all behind the front wall when closed
    bar = build_cabinet(door_pull="bar")
    assert sum(b.name.endswith("pull bar") for b in bar.boards) == 2 and bar.overall()[1] > 22.5
    assert all(b.rot is None for b in doors)                             # closed by default
    opened = build_cabinet(door_open_deg=90, drawer_out=12)
    deg = {b.name: b.rot["deg"] for b in opened.boards if b.rot and ("(door" in b.name or "batten" in b.name)}
    assert all(d == -90 for n, d in deg.items() if "door L" in n or "Door L" in n)   # left leaf hinged on the left
    assert all(d == 90 for n, d in deg.items() if "door R" in n or "Door R" in n)    # right leaf hinged on the right
    assert opened.overall()[1] > 22.5 + 8                                # leaves and drawer swing/slide clear
    out_front = next(b for b in opened.boards if b.name == "Drawer front")
    assert out_front.y == pytest.approx(next(b for b in p.boards if b.name == "Drawer front").y - 12)
    assert not any("(door" in b.name for b in build_cabinet(door=False).boards)
    assert len([b for b in build_cabinet(door_leaves=1).boards if "(door)" in b.name]) == 8
    assert not any(b.group == "drawer" for b in build_cabinet(drawer=False).boards)


def test_open_pose_rotates_the_lids_and_still_fits():
    p = build_cabinet(open_deg=30)
    rotated = [b for b in p.boards if b.rot]
    assert len(rotated) == 4 and all(b.group == "lid" for b in rotated)
    assert p.overall()[2] > 24.0                      # open lids rise above the closed height


def test_slats_on_all_four_sides():
    p = build_cabinet()
    groups = {b.group for b in p.boards}
    assert {"front slat", "back slat", "left slat", "right slat"} <= groups


def test_cutlist_quantities_add_up():
    p = build_cabinet()
    rows = cutlist(p)
    assert sum(r["qty"] for r in rows) == sum(1 for b in p.boards if p.materials[b.material]["kind"] != "hardware")
    assert board_feet(rows)["net_bf"] > 0
    assert "board feet" in to_markdown(p)
    assert to_csv(p).startswith("qty,material")


def test_nesting_fits_and_never_overlaps():
    p = build_cabinet()
    r = nest_sheets(p)
    assert r["sheets"] >= 1
    pl = r["placements"]
    for p_ in pl:
        assert p_["x"] + p_["w"] <= 48 + 1e-6 and p_["y"] + p_["h"] <= 96 + 1e-6
    for i, a in enumerate(pl):
        for b in pl[i + 1:]:
            if a["sheet"] != b["sheet"]:
                continue
            ox = min(a["x"] + a["w"], b["x"] + b["w"]) - max(a["x"], b["x"])
            oy = min(a["y"] + a["h"], b["y"] + b["h"]) - max(a["y"], b["y"])
            assert not (ox > 1e-6 and oy > 1e-6), (a, b)
    assert nest_sheets_svg(r).startswith("<svg")


def test_part_too_big_for_sheet_gives_actionable_error():
    p = build_cabinet()
    with pytest.raises(ValueError, match="does not fit"):
        nest_sheets(p, sheet_w=10, sheet_l=10)


def test_lumber_cutting():
    p = build_cabinet()
    r = cut_lumber(p)
    assert r["total_stock_boards"] >= 1


def test_drawing_is_valid_svg_with_dimensions():
    svg = three_view_svg(build_cabinet())
    assert svg.startswith("<svg") and svg.rstrip().endswith("</svg>")
    assert '24"' in svg and '22 1/2"' in svg
    assert "<polygon" in svg                          # real outlines (arc scoop), not just rectangles


def test_stl_winding_is_outward_for_boxes_arcs_and_cylinders():
    """Signed volume from the written STL facets equals the sum of the parts' own volumes (cuts excluded)."""
    p = build_cabinet()
    stl = to_stl(p, unit_scale=1.0)
    v = [tuple(map(float, m)) for m in re.findall(r"vertex (\S+) (\S+) (\S+)", stl)]
    vol = 0.0
    for i in range(0, len(v), 3):
        a, b, c = v[i], v[i + 1], v[i + 2]
        vol += (a[0] * (b[1] * c[2] - b[2] * c[1]) - a[1] * (b[0] * c[2] - b[2] * c[0]) + a[2] * (b[0] * c[1] - b[1] * c[0])) / 6
    assert vol > 3000 and vol == pytest.approx(mesh_volume(p), rel=1e-6)
    assert skipped_cuts(p) == 7                       # this fallback leaves cuts out and says so
    assert to_obj(p).count("\no ") > 80


def test_triangulate_concave_polygon_covers_its_area():
    poly = [(0, 0), (4, 0), (4, 4), (2, 1), (0, 4)]    # an arrow-head notch: concave
    tris = triangulate(poly)
    area = sum(abs((poly[b][0] - poly[a][0]) * (poly[c][1] - poly[a][1]) -
                   (poly[b][1] - poly[a][1]) * (poly[c][0] - poly[a][0])) / 2 for a, b, c in tris)
    assert area == pytest.approx(abs(sum(poly[i][0] * poly[(i + 1) % 5][1] - poly[(i + 1) % 5][0] * poly[i][1]
                                         for i in range(5)) / 2))


def test_shapes_validate_input():
    with pytest.raises(ValueError):
        sh.prism("ab", [["m", 0, 0]], 0, 1)
    with pytest.raises(ValueError):
        sh.cyl("q", (0, 0, 0), 1, 1)
    assert sh.shape_bbox([sh.box(0, 0, 0, 1, 2, 3), sh.box(0, 0, 0, 9, 9, 9, "cut")])[1] == (1, 2, 3)


def test_json_roundtrip():
    p = build_cabinet()
    q = Project.from_json(p.to_json())
    assert len(q.boards) == len(p.boards) and q.overall() == p.overall()


def test_bad_params_are_explained():
    with pytest.raises(ValueError, match="section_widths"):
        build_cabinet(section_widths=[1, 1, 1, 1, 1])
    with pytest.raises(ValueError, match="Heights"):
        build_cabinet(center_h=30)
    with pytest.raises(ValueError, match="base_z"):
        build_cabinet(base_z=2.0)
    with pytest.raises(ValueError, match="door_pull"):
        build_cabinet(door_pull="knob")
    with pytest.raises(ValueError, match="door_span"):
        build_cabinet(door_span="everywhere")
    with pytest.raises(ValueError, match="door_leaves"):
        build_cabinet(door_leaves=3)
    with pytest.raises(ValueError, match="open them"):
        build_cabinet(drawer_out=5)                    # the drawer is behind closed doors
    with pytest.raises(ValueError, match="open them"):
        build_cabinet(door_open_deg=45, drawer_out=5)  # doors only half open
    with pytest.raises(ValueError, match="drawer_out"):
        build_cabinet(door_open_deg=90, drawer_out=40)
    with pytest.raises(ValueError, match="door_open_deg"):
        build_cabinet(door_open_deg=200)
    with pytest.raises(ValueError, match="foot_arm"):
        build_cabinet(foot_arm=3.5)


def test_frac():
    assert frac(22.5) == '22 1/2"' and frac(0.75) == '3/4"' and frac(24) == '24"' and frac(1.3125) == '1 5/16"'
