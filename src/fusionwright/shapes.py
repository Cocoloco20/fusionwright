"""Backend-neutral solid description.

A part's geometry is a short list of *operations*, each a plain dict (so it survives JSON and can be sent to
Fusion, CadQuery or the pure-Python mesher unchanged):

  box   {"op","k":"box","o":[x,y,z],"s":[sx,sy,sz]}                       axis-aligned box
  prism {"op","k":"prism","pl":"xz"|"yz"|"xy","path":[...],"a","b"}      closed 2-D profile, extruded a -> b
  cyl   {"op","k":"cyl","ax":"x"|"y"|"z","c":[x,y,z],"r","h"}            cylinder centred on c, length h along ax

`op` is "add" (union) or "cut" (subtract). Profile paths use three segment kinds, starting with an "m":
  ["m", u, v]                      move to (start)
  ["l", u, v]                      straight line to
  ["a", um, vm, ue, ve]            circular arc to (ue, ve) passing through (um, vm)
The profile closes back to its start automatically.

Plane conventions (u, v) -> model axes, extrusion axis last:
  xz: u=X, v=Z, extruded along Y      yz: u=Y, v=Z, extruded along X      xy: u=X, v=Y, extruded along Z
Units are inches, X = width, Y = depth (front at Y=0), Z = up.
"""
from __future__ import annotations

import math
from typing import Iterable, Sequence

Vec = tuple[float, float, float]


# ------------------------------------------------------------------ constructors
def box(x, y, z, sx, sy, sz, op="add") -> dict:
    return {"op": op, "k": "box", "o": [x, y, z], "s": [sx, sy, sz]}


def prism(plane: str, path: list, a: float, b: float, op="add") -> dict:
    if plane not in ("xz", "yz", "xy"):
        raise ValueError("plane must be 'xz', 'yz' or 'xy'")
    if not path or path[0][0] != "m":
        raise ValueError("a profile path must start with ['m', u, v]")
    return {"op": op, "k": "prism", "pl": plane, "path": path, "a": a, "b": b}


def cyl(axis: str, c: Sequence[float], r: float, h: float, op="add") -> dict:
    if axis not in ("x", "y", "z"):
        raise ValueError("axis must be 'x', 'y' or 'z'")
    return {"op": op, "k": "cyl", "ax": axis, "c": list(c), "r": r, "h": h}


def polygon(points: Iterable[Sequence[float]]) -> list:
    pts = list(points)
    return [["m", *pts[0]]] + [["l", *p] for p in pts[1:]]


# ------------------------------------------------------------------ geometry helpers
def to3(plane: str, u: float, v: float, w: float) -> Vec:
    if plane == "xz":
        return (u, w, v)
    if plane == "yz":
        return (w, u, v)
    return (u, v, w)


def arc_circle(p0, pm, p1):
    """Circle through three 2-D points -> (cx, cy, r)."""
    (x1, y1), (x2, y2), (x3, y3) = p0, pm, p1
    d = 2 * (x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2))
    if abs(d) < 1e-12:
        raise ValueError("arc points are collinear")
    ux = ((x1**2 + y1**2) * (y2 - y3) + (x2**2 + y2**2) * (y3 - y1) + (x3**2 + y3**2) * (y1 - y2)) / d
    uy = ((x1**2 + y1**2) * (x3 - x2) + (x2**2 + y2**2) * (x1 - x3) + (x3**2 + y3**2) * (x2 - x1)) / d
    return ux, uy, math.hypot(x1 - ux, y1 - uy)


def sample_arc(p0, pm, p1, n: int = 24) -> list[tuple[float, float]]:
    """Points along the arc p0 -> pm -> p1 (excluding p0, including p1)."""
    cx, cy, r = arc_circle(p0, pm, p1)
    a0, am, a1 = (math.atan2(p[1] - cy, p[0] - cx) for p in (p0, pm, p1))
    two = 2 * math.pi
    # sweep direction is whichever passes through pm
    ccw = ((am - a0) % two) < ((a1 - a0) % two)
    sweep = ((a1 - a0) % two) if ccw else -((a0 - a1) % two)
    return [(cx + r * math.cos(a0 + sweep * i / n), cy + r * math.sin(a0 + sweep * i / n)) for i in range(1, n + 1)]


def outline(path: list, n: int = 24) -> list[tuple[float, float]]:
    """Closed polygon for a profile path (arcs sampled into n segments)."""
    pts: list[tuple[float, float]] = []
    for seg in path:
        if seg[0] in ("m", "l"):
            pts.append((seg[1], seg[2]))
        else:
            pts.extend(sample_arc(pts[-1], (seg[1], seg[2]), (seg[3], seg[4]), n))
    if len(pts) > 1 and math.hypot(pts[0][0] - pts[-1][0], pts[0][1] - pts[-1][1]) < 1e-9:
        pts.pop()
    return pts


def op_bbox(op: dict) -> tuple[Vec, Vec]:
    k = op["k"]
    if k == "box":
        o, s = op["o"], op["s"]
        return tuple(o), (o[0] + s[0], o[1] + s[1], o[2] + s[2])
    if k == "cyl":
        c, r, h, ax = op["c"], op["r"], op["h"], op["ax"]
        ext = [r, r, r]
        ext["xyz".index(ax)] = h / 2
        return (c[0] - ext[0], c[1] - ext[1], c[2] - ext[2]), (c[0] + ext[0], c[1] + ext[1], c[2] + ext[2])
    pts2 = outline(op["path"], 64)
    pts = [to3(op["pl"], u, v, w) for (u, v) in pts2 for w in (op["a"], op["b"])]
    return (tuple(min(p[i] for p in pts) for i in range(3)), tuple(max(p[i] for p in pts) for i in range(3)))


def shape_bbox(shape: list[dict]) -> tuple[Vec, Vec]:
    """Bounding box of everything that is *added* (cuts never grow a part)."""
    boxes = [op_bbox(o) for o in shape if o["op"] == "add"]
    if not boxes:
        raise ValueError("a shape needs at least one 'add' operation")
    return (tuple(min(b[0][i] for b in boxes) for i in range(3)),
            tuple(max(b[1][i] for b in boxes) for i in range(3)))


def rotate_point(p: Vec, rot: dict) -> Vec:
    """Rotate p about the axis through rot['o'] with direction rot['ax'] by rot['deg'] (right-hand rule)."""
    ox, oy, oz = rot["o"]
    ax = rot["ax"]
    n = math.sqrt(sum(c * c for c in ax))
    kx, ky, kz = (c / n for c in ax)
    t = math.radians(rot["deg"])
    ct, st = math.cos(t), math.sin(t)
    vx, vy, vz = p[0] - ox, p[1] - oy, p[2] - oz
    dot = kx * vx + ky * vy + kz * vz
    cx = ky * vz - kz * vy
    cy = kz * vx - kx * vz
    cz = kx * vy - ky * vx
    return (ox + vx * ct + cx * st + kx * dot * (1 - ct),
            oy + vy * ct + cy * st + ky * dot * (1 - ct),
            oz + vz * ct + cz * st + kz * dot * (1 - ct))


def rotated_bbox(lo: Vec, hi: Vec, rot: dict) -> tuple[Vec, Vec]:
    corners = [rotate_point((x, y, z), rot) for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])]
    return (tuple(min(c[i] for c in corners) for i in range(3)), tuple(max(c[i] for c in corners) for i in range(3)))
