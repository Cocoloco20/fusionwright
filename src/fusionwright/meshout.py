"""Dependency-free STL / OBJ export of a Project (boards are boxes), so a model can be produced with
no CAD software at all. Units: inches -> millimetres by default (STL consumers expect mm)."""
from __future__ import annotations

from .model import Board, Project

_FACES = [  # (normal, 4 corner indices into the 8 box corners), counter-clockwise from outside
    ((0, 0, -1), (0, 2, 3, 1)), ((0, 0, 1), (4, 5, 7, 6)),
    ((0, -1, 0), (0, 1, 5, 4)), ((0, 1, 0), (2, 6, 7, 3)),
    ((-1, 0, 0), (0, 4, 6, 2)), ((1, 0, 0), (1, 3, 7, 5)),
]


def _corners(b: Board, k: float):
    x0, y0, z0 = b.x * k, b.y * k, b.z * k
    x1, y1, z1 = x0 + b.sx * k, y0 + b.sy * k, z0 + b.sz * k
    return [(x, y, z) for z in (z0, z1) for y in (y0, y1) for x in (x0, x1)]


def to_stl(project: Project, unit_scale: float = 25.4) -> str:
    out = [f"solid {project.name.replace(' ', '_')}"]
    for b in project.boards:
        c = _corners(b, unit_scale)
        for n, (a, b_, c_, d) in _FACES:
            for tri in ((a, b_, c_), (a, c_, d)):
                out.append(f"facet normal {n[0]} {n[1]} {n[2]}\n outer loop")
                for i in tri:
                    out.append("  vertex %.5f %.5f %.5f" % c[i])
                out.append(" endloop\nendfacet")
    out.append(f"endsolid {project.name.replace(' ', '_')}")
    return "\n".join(out) + "\n"


def to_obj(project: Project, unit_scale: float = 25.4) -> str:
    out = [f"# {project.name} (units: mm)"]
    base = 1
    for b in project.boards:
        out.append(f"o {b.name.replace(' ', '_')}")
        for v in _corners(b, unit_scale):
            out.append("v %.5f %.5f %.5f" % v)
        for _, quad in _FACES:
            out.append("f " + " ".join(str(base + i) for i in quad))
        base += 8
    return "\n".join(out) + "\n"
