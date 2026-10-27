"""Dependency-free STL / OBJ export of a Project, so a model can be produced with no CAD software at all.

Boxes, extruded profiles (including arcs) and cylinders are meshed directly; hinge rotations are applied. Cut
operations need real boolean geometry, so this fallback leaves them out and reports how many it skipped; install
the open-source CAD extra (`pip install "fusionwright[cad]"`) for exact solids with every cut.
Units: inches -> millimetres by default (STL consumers expect mm).
"""
from __future__ import annotations

import math

from . import shapes as sh
from .model import Board, Project

Tri = tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]


# ------------------------------------------------------------------ polygon triangulation (ear clipping)
def _area(poly) -> float:
    return sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1]
               for i in range(len(poly))) / 2


def _in_tri(p, a, b, c) -> bool:
    d1 = (p[0] - b[0]) * (a[1] - b[1]) - (a[0] - b[0]) * (p[1] - b[1])
    d2 = (p[0] - c[0]) * (b[1] - c[1]) - (b[0] - c[0]) * (p[1] - c[1])
    d3 = (p[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (p[1] - a[1])
    return not ((d1 < 0 or d2 < 0 or d3 < 0) and (d1 > 0 or d2 > 0 or d3 > 0))


def triangulate(poly: list[tuple[float, float]]) -> list[tuple[int, int, int]]:
    """Index triples (counter-clockwise) covering a simple polygon."""
    n = len(poly)
    idx = list(range(n))
    if _area(poly) < 0:
        idx.reverse()
    out: list[tuple[int, int, int]] = []
    guard = 0
    while len(idx) > 3 and guard < 10 * n * n:
        guard += 1
        for k in range(len(idx)):
            i0, i1, i2 = idx[k - 1], idx[k], idx[(k + 1) % len(idx)]
            a, b, c = poly[i0], poly[i1], poly[i2]
            if (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]) <= 1e-12:
                continue
            if any(_in_tri(poly[j], a, b, c) for j in idx if j not in (i0, i1, i2)):
                continue
            out.append((i0, i1, i2))
            idx.pop(k)
            break
        else:
            break
    if len(idx) == 3:
        out.append((idx[0], idx[1], idx[2]))
    return out


# ------------------------------------------------------------------ primitives -> triangles
def _box_tris(o, s) -> list[Tri]:
    x0, y0, z0 = o
    x1, y1, z1 = x0 + s[0], y0 + s[1], z0 + s[2]
    c = [(x, y, z) for z in (z0, z1) for y in (y0, y1) for x in (x0, x1)]
    quads = [(0, 2, 3, 1), (4, 5, 7, 6), (0, 1, 5, 4), (2, 6, 7, 3), (0, 4, 6, 2), (1, 3, 7, 5)]
    tris: list[Tri] = []
    for a, b, c_, d in quads:
        tris += [(c[a], c[b], c[c_]), (c[a], c[c_], c[d])]
    return tris


def _extrude_tris(poly2d, plane: str, a: float, b: float) -> list[Tri]:
    n = len(poly2d)
    p0 = [sh.to3(plane, u, v, a) for u, v in poly2d]
    p1 = [sh.to3(plane, u, v, b) for u, v in poly2d]
    tris: list[Tri] = []
    for i, j, k in triangulate(poly2d):
        tris.append((p0[i], p0[k], p0[j]))
        tris.append((p1[i], p1[j], p1[k]))
    for i in range(n):
        j = (i + 1) % n
        tris += [(p0[i], p0[j], p1[j]), (p0[i], p1[j], p1[i])]
    return tris


def _cyl_tris(ax: str, c, r: float, h: float, seg: int = 48) -> list[Tri]:
    i = "xyz".index(ax)
    poly = [(r * math.cos(2 * math.pi * k / seg), r * math.sin(2 * math.pi * k / seg)) for k in range(seg)]
    # a cylinder is an extrusion of a circle along its axis; map the circle onto the two other axes
    plane = {"x": "yz", "y": "xz", "z": "xy"}[ax]
    u0, v0 = {"yz": (c[1], c[2]), "xz": (c[0], c[2]), "xy": (c[0], c[1])}[plane]
    poly = [(u0 + u, v0 + v) for u, v in poly]
    return _extrude_tris(poly, plane, c[i] - h / 2, c[i] + h / 2)


def _signed_volume(tris: list[Tri]) -> float:
    v = 0.0
    for a, b, c in tris:
        v += (a[0] * (b[1] * c[2] - b[2] * c[1]) - a[1] * (b[0] * c[2] - b[2] * c[0]) + a[2] * (b[0] * c[1] - b[1] * c[0])) / 6
    return v


def part_triangles(b: Board) -> tuple[list[Tri], int]:
    """Outward-facing triangles for one part (hinge rotation applied) and the number of cuts skipped."""
    ops = b.shape if b.shape is not None else [sh.box(b.x, b.y, b.z, b.sx, b.sy, b.sz)]
    tris: list[Tri] = []
    skipped = 0
    for op in ops:
        if op["op"] != "add":
            skipped += 1
            continue
        if op["k"] == "box":
            t = _box_tris(op["o"], op["s"])
        elif op["k"] == "cyl":
            t = _cyl_tris(op["ax"], op["c"], op["r"], op["h"])
        else:
            t = _extrude_tris(sh.outline(op["path"], 32), op["pl"], op["a"], op["b"])
        if _signed_volume(t) < 0:                    # one consistent outward winding per primitive
            t = [(x, z, y) for x, y, z in t]
        tris += t
    if b.rot:
        tris = [tuple(sh.rotate_point(p, b.rot) for p in tri) for tri in tris]       # type: ignore[misc]
    return tris, skipped


def mesh_volume(project: Project) -> float:
    """Signed volume of the exported mesh in cubic inches (adds only; overlapping adds count twice)."""
    return sum(_signed_volume(part_triangles(b)[0]) for b in project.boards)


def skipped_cuts(project: Project) -> int:
    return sum(part_triangles(b)[1] for b in project.boards)


def _normal(a, b, c):
    ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    n = (uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx)
    ln = math.sqrt(sum(q * q for q in n)) or 1.0
    return tuple(q / ln for q in n)


def to_stl(project: Project, unit_scale: float = 25.4) -> str:
    nm = project.name.replace(" ", "_")
    out = [f"solid {nm}"]
    for b in project.boards:
        for tri in part_triangles(b)[0]:
            t = [tuple(q * unit_scale for q in p) for p in tri]
            n = _normal(*t)
            out.append(f"facet normal {n[0]:.6f} {n[1]:.6f} {n[2]:.6f}\n outer loop")
            for p in t:
                out.append("  vertex %.5f %.5f %.5f" % p)
            out.append(" endloop\nendfacet")
    out.append(f"endsolid {nm}")
    return "\n".join(out) + "\n"


def to_obj(project: Project, unit_scale: float = 25.4) -> str:
    out = [f"# {project.name} (units: mm; cuts are only included by the CAD backend)"]
    base = 1
    for b in project.boards:
        tris = part_triangles(b)[0]
        if not tris:
            continue
        out.append(f"o {b.name.replace(' ', '_')}")
        for tri in tris:
            for p in tri:
                out.append("v %.5f %.5f %.5f" % tuple(q * unit_scale for q in p))
        for k in range(len(tris)):
            out.append(f"f {base + 3 * k} {base + 3 * k + 1} {base + 3 * k + 2}")
        base += 3 * len(tris)
    return "\n".join(out) + "\n"
