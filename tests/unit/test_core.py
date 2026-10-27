import math, re
from fusionwright.cabinet import build_cabinet
from fusionwright.cutlist import cutlist, board_feet, to_markdown, to_csv
from fusionwright.nesting import nest_sheets, nest_sheets_svg, cut_lumber
from fusionwright.drawings import three_view_svg
from fusionwright.meshout import to_stl, to_obj
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


def test_slats_on_all_four_sides():
    p = build_cabinet()
    groups = {b.group for b in p.boards}
    assert {"front slat", "back slat", "left slat", "right slat"} <= groups


def test_cutlist_quantities_add_up():
    p = build_cabinet()
    rows = cutlist(p)
    assert sum(r["qty"] for r in rows) == len(p.boards)
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


def test_stl_has_positive_volume():
    """Signed volume from facets == sum of box volumes (checks winding is outward)."""
    p = build_cabinet()
    stl = to_stl(p, unit_scale=1.0)
    v = [tuple(map(float, m)) for m in re.findall(r"vertex (\S+) (\S+) (\S+)", stl)]
    vol = 0.0
    for i in range(0, len(v), 3):
        a, b, c = v[i], v[i + 1], v[i + 2]
        vol += (a[0] * (b[1] * c[2] - b[2] * c[1]) - a[1] * (b[0] * c[2] - b[2] * c[0]) + a[2] * (b[0] * c[1] - b[1] * c[0])) / 6
    assert vol == pytest.approx(sum(b.volume for b in p.boards), rel=1e-6)
    assert to_obj(p).count("\nv ") == 8 * len(p.boards)


def test_json_roundtrip():
    p = build_cabinet()
    q = Project.from_json(p.to_json())
    assert len(q.boards) == len(p.boards) and q.overall() == p.overall()


def test_bad_params_are_explained():
    with pytest.raises(ValueError, match="section_widths"):
        build_cabinet(section_widths=[1, 1, 1, 1, 1])
    with pytest.raises(ValueError, match="Heights"):
        build_cabinet(center_h=30)


def test_frac():
    assert frac(22.5) == '22 1/2"' and frac(0.75) == '3/4"' and frac(24) == '24"' and frac(1.3125) == '1 5/16"'
