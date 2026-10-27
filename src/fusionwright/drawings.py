"""Builder drawings as SVG (no CAD, no cloud): front / top / right-side views, overall and per-section
dimensions, title block. Sheet is ANSI B landscape (17 x 11 in) at 100 px per sheet inch."""
from __future__ import annotations

from datetime import date
from xml.sax.saxutils import escape

from .model import Project, frac

PX = 100            # sheet px per sheet inch
SHEET_W, SHEET_H = 17 * PX, 11 * PX
MARGIN = int(0.75 * PX)
TITLE_H = int(1.1 * PX)


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

    # front view (looking +Y): far boards (large Y) first
    out.append(f'<g id="front">')
    for b in sorted(project.boards, key=lambda b: -b.y):
        out.append(f'<rect class="b" x="{fx0 + b.x * s:.1f}" y="{fy0 + (H - b.z - b.sz) * s:.1f}" '
                   f'width="{b.sx * s:.1f}" height="{b.sz * s:.1f}" fill="{color(b)}"/>')
    out.append('</g>')
    # top view (looking down): low Z first
    out.append('<g id="top">')
    for b in sorted(project.boards, key=lambda b: b.z):
        out.append(f'<rect class="b" x="{fx0 + b.x * s:.1f}" y="{top_y0 + (D - b.y - b.sy) * s:.1f}" '
                   f'width="{b.sx * s:.1f}" height="{b.sy * s:.1f}" fill="{color(b)}"/>')
    for f in project.features:
        if f.get("type") == "finger_pull":
            cx, cy = f["center"]
            out.append(f'<circle cx="{fx0 + cx * s:.1f}" cy="{top_y0 + (D - cy) * s:.1f}" r="{f["dia"] / 2 * s:.1f}" '
                       'fill="white" stroke="#111" stroke-width=".8"/>')
    out.append('</g>')
    # right-side view (viewer at +X): small X first; front (Y=0) is on the left
    out.append('<g id="side">')
    for b in sorted(project.boards, key=lambda b: b.x):
        out.append(f'<rect class="b" x="{side_x0 + b.y * s:.1f}" y="{fy0 + (H - b.z - b.sz) * s:.1f}" '
                   f'width="{b.sy * s:.1f}" height="{b.sz * s:.1f}" fill="{color(b)}"/>')
    out.append('</g>')

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
