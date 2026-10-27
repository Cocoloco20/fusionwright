"""Builder drawings as SVG (no CAD, no cloud): front / top / right-side views, overall and per-section
dimensions, title block. Sheet is ANSI B landscape (17 x 11 in) at 100 px per sheet inch."""
from __future__ import annotations

import math
from datetime import date
from xml.sax.saxutils import escape

from . import shapes as sh
from .model import Board, Project, frac

PX = 100            # sheet px per sheet inch
SHEET_W, SHEET_H = 17 * PX, 11 * PX
MARGIN = int(0.75 * PX)
TITLE_H = int(1.1 * PX)


def _hull(pts):
    pts = sorted(set((round(x, 6), round(y, 6)) for x, y in pts))
    if len(pts) <= 2:
        return pts
    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo, up = [], []
    for q in pts:
        while len(lo) >= 2 and cross(lo[-2], lo[-1], q) <= 0:
            lo.pop()
        lo.append(q)
    for q in reversed(pts):
        while len(up) >= 2 and cross(up[-2], up[-1], q) <= 0:
            up.pop()
        up.append(q)
    return lo[:-1] + up[:-1]


# view -> which model axes become the drawing's (right, up) coordinates, and the axis the viewer looks along
_AXES = {"front": (0, 2, 1), "top": (0, 1, 2), "side": (1, 2, 0)}


def _part_polys(b: Board, view: str) -> list[tuple[str, list[tuple[float, float]]]]:
    """[(op, polygon)] silhouette of each shape operation of a part, in model inches projected for `view`.
    A profile viewed along its extrusion axis keeps its true outline (arcs included); everything else is
    drawn as its bounding rectangle, and hinged-open parts as the hull of their rotated box."""
    ui, vi, wi = _AXES[view]
    ops = b.shape if b.shape is not None else [sh.box(b.x, b.y, b.z, b.sx, b.sy, b.sz)]
    out = []
    for op in ops:
        lo, hi = sh.op_bbox(op)
        if b.rot:
            corners = [sh.rotate_point((x, y, z), b.rot) for x in (lo[0], hi[0]) for y in (lo[1], hi[1])
                       for z in (lo[2], hi[2])]
            out.append((op["op"], _hull([(c[ui], c[vi]) for c in corners])))
            continue
        poly = None
        if op["k"] == "prism":
            axis = {"xz": 1, "yz": 0, "xy": 2}[op["pl"]]
            if axis == wi:
                poly = [(sh.to3(op["pl"], u, v, 0)[ui], sh.to3(op["pl"], u, v, 0)[vi]) for u, v in sh.outline(op["path"], 48)]
        elif op["k"] == "cyl" and "xyz".index(op["ax"]) == wi:
            c = op["c"]
            poly = [(c[ui] + op["r"] * math.cos(2 * math.pi * k / 36), c[vi] + op["r"] * math.sin(2 * math.pi * k / 36))
                    for k in range(36)]
        if poly is None:
            poly = [(lo[ui], lo[vi]), (hi[ui], lo[vi]), (hi[ui], hi[vi]), (lo[ui], hi[vi])]
        out.append((op["op"], poly))
    return out


def _scale_label(s: float) -> str:
    ratio = PX / s                     # model inches represented by one sheet inch
    for nice in (1, 2, 3, 4, 6, 8, 12, 16):
        if abs(ratio - nice) < 0.25:
            return f"1:{nice}" if nice > 1 else "1:1"
    return f"1:{ratio:.1f}"


def _dim_h(x0, x1, y, text, out, off=18):
    yy = y + off
    out.append(f'<line x1="{x0}" y1="{y + 4}" x2="{x0}" y2="{yy + 4}" class="ext"/>'
               f'<line x1="{x1}" y1="{y + 4}" x2="{x1}" y2="{yy + 4}" class="ext"/>'
               f'<line x1="{x0}" y1="{yy}" x2="{x1}" y2="{yy}" class="dim"/>'
               f'<line x1="{x0}" y1="{yy - 4}" x2="{x0 + 8}" y2="{yy}" class="dim"/>'
               f'<line x1="{x0}" y1="{yy + 4}" x2="{x0 + 8}" y2="{yy}" class="dim"/>'
               f'<line x1="{x1}" y1="{yy - 4}" x2="{x1 - 8}" y2="{yy}" class="dim"/>'
               f'<line x1="{x1}" y1="{yy + 4}" x2="{x1 - 8}" y2="{yy}" class="dim"/>'
               f'<text x="{(x0 + x1) / 2}" y="{yy - 4}" text-anchor="middle" class="dt">{escape(text)}</text>')


def _dim_v(x, y0, y1, text, out, off=-18):
    xx = x + off
    out.append(f'<line x1="{x - 4}" y1="{y0}" x2="{xx - 4}" y2="{y0}" class="ext"/>'
               f'<line x1="{x - 4}" y1="{y1}" x2="{xx - 4}" y2="{y1}" class="ext"/>'
               f'<line x1="{xx}" y1="{y0}" x2="{xx}" y2="{y1}" class="dim"/>'
               f'<line x1="{xx - 4}" y1="{y0}" x2="{xx}" y2="{y0 + 8}" class="dim"/>'
               f'<line x1="{xx + 4}" y1="{y0}" x2="{xx}" y2="{y0 + 8}" class="dim"/>'
               f'<line x1="{xx - 4}" y1="{y1}" x2="{xx}" y2="{y1 - 8}" class="dim"/>'
               f'<line x1="{xx + 4}" y1="{y1}" x2="{xx}" y2="{y1 - 8}" class="dim"/>'
               f'<text x="{xx - 5}" y="{(y0 + y1) / 2}" text-anchor="middle" class="dt" '
               f'transform="rotate(-90 {xx - 5} {(y0 + y1) / 2})">{escape(text)}</text>')


def three_view_svg(project: Project) -> str:
    W, D, H = project.overall()
    avail_w = SHEET_W - 2 * MARGIN - 80
    avail_h = SHEET_H - 2 * MARGIN - TITLE_H - 80
    s = min(avail_w / (W + D), avail_h / (H + D))
    gap = 70
    fx0 = MARGIN + 50
    fy0 = SHEET_H - MARGIN - TITLE_H - 40 - H * s          # top-left of the front view
    top_y0 = fy0 - gap - D * s                             # top view sits above the front view
    side_x0 = fx0 + W * s + gap                            # right-side view sits to the right
    mats = project.materials

    def color(b):
        return mats.get(b.material, {}).get("color", "#ccc")

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {SHEET_W} {SHEET_H}" width="{SHEET_W}" '
           f'height="{SHEET_H}" font-family="Helvetica, Arial, sans-serif">',
           '<style>.ext{stroke:#555;stroke-width:.6}.dim{stroke:#111;stroke-width:.9}.dt{font-size:12px;fill:#111}'
           '.lbl{font-size:13px;font-weight:bold;fill:#111}.b{stroke:#222;stroke-width:.7}</style>',
           f'<rect width="{SHEET_W}" height="{SHEET_H}" fill="white"/>',
           f'<rect x="{MARGIN / 2}" y="{MARGIN / 2}" width="{SHEET_W - MARGIN}" height="{SHEET_H - MARGIN}" '
           'fill="none" stroke="#111" stroke-width="2"/>']

    def poly_svg(poly, mapper, fill, cut=False):
        pts = " ".join("%.1f,%.1f" % mapper(u, v) for u, v in poly)
        if cut:
            return f'<polygon points="{pts}" fill="#000" fill-opacity=".28" stroke="#222" stroke-width=".5"/>'
        return f'<polygon class="b" points="{pts}" fill="{fill}"/>'

    def draw(view, key, mapper, depth_key):
        out.append(f'<g id="{view}">')
        for b in sorted(project.boards, key=depth_key):
            for op, poly in _part_polys(b, view):
                out.append(poly_svg(poly, mapper, color(b), cut=(op == "cut")))
        out.append('</g>')

    # front view (looking +Y): far boards (large Y) first; top view (looking down): low Z first;
    # right-side view (viewer at +X, front at the left): small X first
    draw("front", "f", lambda u, v: (fx0 + u * s, fy0 + (H - v) * s), lambda b: -b.y)
    draw("top", "t", lambda u, v: (fx0 + u * s, top_y0 + (D - v) * s), lambda b: b.z)
    draw("side", "s", lambda u, v: (side_x0 + u * s, fy0 + (H - v) * s), lambda b: b.x)

    # labels
    out.append(f'<text x="{fx0}" y="{fy0 + H * s + 52}" class="lbl">FRONT</text>')
    out.append(f'<text x="{fx0}" y="{top_y0 - 8}" class="lbl">TOP</text>')
    out.append(f'<text x="{side_x0}" y="{fy0 + H * s + 52}" class="lbl">RIGHT SIDE (front at left)</text>')

    # dimensions
    _dim_h(fx0, fx0 + W * s, fy0 + H * s, frac(W), out)
    _dim_v(fx0, fy0, fy0 + H * s, frac(H), out, off=-24)
    _dim_h(side_x0, side_x0 + D * s, fy0 + H * s, frac(D), out)
    # per-section heights (lids) along the top of the front view
    lids = [b for b in project.boards if b.group == "lid"]
    for b in sorted(lids, key=lambda b: b.x):
        top = b.z + b.sz
        out.append(f'<text x="{fx0 + (b.x + b.sx / 2) * s:.1f}" y="{fy0 + (H - top) * s - 6:.1f}" text-anchor="middle" '
                   f'class="dt">{frac(top)}</text>')

    # title block
    tx, ty = SHEET_W - MARGIN / 2 - 6 * PX, SHEET_H - MARGIN / 2 - TITLE_H
    out.append(f'<rect x="{tx}" y="{ty}" width="{6 * PX}" height="{TITLE_H}" fill="white" stroke="#111" stroke-width="1.5"/>')
    out.append(f'<text x="{tx + 12}" y="{ty + 30}" font-size="20" font-weight="bold">{escape(project.name)}</text>')
    out.append(f'<text x="{tx + 12}" y="{ty + 54}" font-size="12">Overall {frac(W)} W x {frac(D)} D x {frac(H)} H   '
               f'|  Units: inches  |  Scale {_scale_label(s)}</text>')
    out.append(f'<text x="{tx + 12}" y="{ty + 74}" font-size="12">Boards: {len(project.boards)}  |  '
               f'Drawn {date.today().isoformat()}  |  Generated by fusionwright</text>')
    out.append(f'<text x="{tx + 12}" y="{ty + 94}" font-size="10" fill="#555">Third-angle projection. '
               'Verify all dimensions before cutting.</text>')
    out.append('</svg>')
    return "\n".join(out)
