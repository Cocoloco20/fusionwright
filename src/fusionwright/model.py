"""Backend-neutral project model used by the add-ons (e.g. the woodworking one): a project is a list of parts ("boards").

Everything here is plain Python (no CAD needed). Units are inches, X = width, Y = depth
(front at Y=0), Z = up. A part carries its bounding box (x, y, z, sx, sy, sz) and, when it is not a plain
rectangular board, a `shape` (see shapes.py: prisms with arcs, cylinders, cuts) and an optional `rot`
(hinge rotation). The bounding box is always the *unrotated* extent, which is what a cut list needs.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

from . import shapes as sh

SOLID = "solid"      # solid lumber (priced by board foot)
SHEET = "sheet"      # sheet goods such as plywood (priced by sheet)


@dataclass
class Board:
    name: str
    group: str                 # e.g. "front slat", "lid"
    material: str              # key into Project.materials
    x: float
    y: float
    z: float
    sx: float
    sy: float
    sz: float
    grain: str = "z"           # axis the grain runs along: x | y | z
    shape: list | None = None  # None = plain box; otherwise a list of shape operations (shapes.py)
    rot: dict | None = None    # {"o": [x,y,z], "ax": [x,y,z], "deg": float}: hinge rotation about an axis
    note: str = ""

    @classmethod
    def from_shape(cls, name: str, group: str, material: str, shape: list, rot: dict | None = None,
                   grain: str = "z", note: str = "") -> "Board":
        lo, hi = sh.shape_bbox(shape)
        return cls(name, group, material, lo[0], lo[1], lo[2], hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2],
                   grain, shape, rot, note)

    @property
    def is_box(self) -> bool:
        return self.shape is None and self.rot is None

    def world_bbox(self):
        """Bounding box in the assembled model (applies the hinge rotation if any)."""
        lo, hi = (self.x, self.y, self.z), self.max_corner
        if self.rot:
            lo, hi = sh.rotated_bbox(lo, hi, self.rot)
        return lo, hi

    @property
    def size(self) -> tuple[float, float, float]:
        return (self.sx, self.sy, self.sz)

    @property
    def thickness(self) -> float:
        return min(self.size)

    @property
    def length(self) -> float:
        return max(self.size)

    @property
    def width(self) -> float:
        return sorted(self.size)[1]

    @property
    def volume(self) -> float:
        return self.sx * self.sy * self.sz

    @property
    def max_corner(self) -> tuple[float, float, float]:
        return (self.x + self.sx, self.y + self.sy, self.z + self.sz)


@dataclass
class Project:
    name: str
    boards: list[Board] = field(default_factory=list)
    materials: dict[str, dict[str, Any]] = field(default_factory=dict)   # key -> {label, kind, color}
    hardware: list[dict[str, Any]] = field(default_factory=list)
    features: list[dict[str, Any]] = field(default_factory=list)         # e.g. finger pulls
    params: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    # -- geometry helpers ---------------------------------------------------------
    def bounds(self) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
        if not self.boards:
            return (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)
        wb = [b.world_bbox() for b in self.boards]
        lo = tuple(min(w[0][i] for w in wb) for i in range(3))
        hi = tuple(max(w[1][i] for w in wb) for i in range(3))
        return lo, hi

    def overall(self) -> tuple[float, float, float]:
        lo, hi = self.bounds()
        return (hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2])

    def interferences(self, tol: float = 1e-6) -> list[tuple[str, str, float]]:
        """Pairs of plain boxes whose volumes overlap (exact). Shaped or rotated parts are skipped here; the CAD
        backends check those with the real kernel (cad_check / fusion_check)."""
        out = []
        bs = [b for b in self.boards if b.is_box]
        for i in range(len(bs)):
            a = bs[i]
            for j in range(i + 1, len(bs)):
                b = bs[j]
                dx = min(a.max_corner[0], b.max_corner[0]) - max(a.x, b.x)
                dy = min(a.max_corner[1], b.max_corner[1]) - max(a.y, b.y)
                dz = min(a.max_corner[2], b.max_corner[2]) - max(a.z, b.z)
                if dx > tol and dy > tol and dz > tol:
                    out.append((a.name, b.name, dx * dy * dz))
        return out

    # -- (de)serialisation --------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Project":
        d = dict(d)
        d["boards"] = [Board(**b) for b in d.get("boards", [])]
        return cls(**d)

    @classmethod
    def from_json(cls, s: str) -> "Project":
        return cls.from_dict(json.loads(s))


def frac(x: float, denom: int = 16) -> str:
    """Format inches as a woodworker would: 22 1/2", 3/4", 1 5/16"."""
    neg = x < 0
    x = abs(x)
    whole = int(x)
    n = round((x - whole) * denom)
    if n == denom:
        whole, n = whole + 1, 0
    while n and n % 2 == 0:
        n //= 2
        denom //= 2
    s = ""
    if whole or not n:
        s = str(whole)
    if n:
        s = (s + " " if s else "") + f"{n}/{denom}"
    return ("-" if neg else "") + s + '"'
