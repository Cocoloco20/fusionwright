"""Backend-neutral project model: a furniture project is a list of rectangular boards.

Everything here is plain Python (no CAD needed). Units are inches, X = width, Y = depth
(front at Y=0), Z = up. A board is an axis-aligned box described by its minimum corner and
its extents.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

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
        lo = (min(b.x for b in self.boards), min(b.y for b in self.boards), min(b.z for b in self.boards))
        hi = (max(b.max_corner[0] for b in self.boards), max(b.max_corner[1] for b in self.boards),
              max(b.max_corner[2] for b in self.boards))
        return lo, hi

    def overall(self) -> tuple[float, float, float]:
        lo, hi = self.bounds()
        return (hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2])

    def interferences(self, tol: float = 1e-6) -> list[tuple[str, str, float]]:
        """Pairs of boards whose volumes overlap (exact for axis-aligned boxes)."""
        out = []
        bs = self.boards
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
