"""Open-source CAD backend: builds a Project with CadQuery (OpenCascade), no Autodesk software needed.

Install the extra:  pip install "fusionwright[cad]"

What it gives you: exact solids (arcs, cuts, hinge rotation), kernel interference checks, STEP (names + colours),
STL, and shaded preview images. Units in the Project are inches; STEP/STL are written in millimetres.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from .. import shapes as sh
from ..model import Board, Project

INSTALL_HINT = 'The open-source CAD backend needs CadQuery. Install it with:  pip install "fusionwright[cad]"'


def _cq():
    try:
        import cadquery as cq
        return cq
    except ImportError as e:                                       # pragma: no cover
        raise RuntimeError(INSTALL_HINT) from e


def available() -> bool:
    try:
        _cq()
        return True
    except RuntimeError:
        return False


def _v(cq, p):
    return cq.Vector(*p)


def _prim(cq, op: dict):
    k = op["k"]
    if k == "box":
        return cq.Solid.makeBox(*op["s"], pnt=_v(cq, op["o"]))
    if k == "cyl":
        d = {"x": (1, 0, 0), "y": (0, 1, 0), "z": (0, 0, 1)}[op["ax"]]
        c = op["c"]
        base = (c[0] - d[0] * op["h"] / 2, c[1] - d[1] * op["h"] / 2, c[2] - d[2] * op["h"] / 2)
        return cq.Solid.makeCylinder(op["r"], op["h"], _v(cq, base), _v(cq, d))
    # prism: draw the profile on a plane whose local (x, y) are the profile's (u, v), extrude a -> b
    a, b, pl = op["a"], op["b"], op["pl"]
    if pl == "xz":                          # normal -Y: start at y=b and extrude (b-a) toward -Y
        plane = cq.Plane(origin=(0, b, 0), xDir=(1, 0, 0), normal=(0, -1, 0))
    elif pl == "yz":
        plane = cq.Plane(origin=(a, 0, 0), xDir=(0, 1, 0), normal=(1, 0, 0))
    else:
        plane = cq.Plane(origin=(0, 0, a), xDir=(1, 0, 0), normal=(0, 0, 1))
    wp = cq.Workplane(plane)
    path = op["path"]
    wp = wp.moveTo(path[0][1], path[0][2])
    for seg in path[1:]:
        wp = wp.lineTo(seg[1], seg[2]) if seg[0] == "l" else wp.threePointArc((seg[1], seg[2]), (seg[3], seg[4]))
    return wp.close().extrude(b - a).val()


def part_solid(b: Board):
    """CadQuery shape for one part (hinge rotation applied)."""
    cq = _cq()
    ops = b.shape if b.shape is not None else [sh.box(b.x, b.y, b.z, b.sx, b.sy, b.sz)]
    result = None
    for op in ops:
        s = _prim(cq, op)
        if op["op"] == "add":
            result = s if result is None else result.fuse(s).clean()
        else:
            if result is None:
                raise ValueError(f"{b.name}: a cut needs a prior add")
            result = result.cut(s).clean()
    if b.rot:
        o, ax = b.rot["o"], b.rot["ax"]
        result = result.rotate(_v(cq, o), _v(cq, (o[0] + ax[0], o[1] + ax[1], o[2] + ax[2])), b.rot["deg"])
    return result


def build_all(project: Project) -> dict[str, Any]:
    return {b.name: part_solid(b) for b in project.boards}


def _hex_rgb(h: str) -> tuple[float, float, float]:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def interferences(project: Project, solids: dict | None = None, min_volume_in3: float = 1e-4) -> list[dict]:
    """Exact overlapping volume for every pair of parts whose boxes touch (kernel boolean)."""
    solids = solids or build_all(project)
    boxes = {b.name: b.world_bbox() for b in project.boards}
    names = list(solids)
    out = []
    for i, a in enumerate(names):
        for c in names[i + 1:]:
            (alo, ahi), (clo, chi) = boxes[a], boxes[c]
            if any(min(ahi[k], chi[k]) - max(alo[k], clo[k]) <= 1e-6 for k in range(3)):
                continue
            try:
                vol = solids[a].intersect(solids[c]).Volume()
            except Exception:
                continue
            if vol > min_volume_in3:
                out.append({"a": a, "b": c, "volume_in3": round(vol, 4)})
    return out


def stats(project: Project, solids: dict | None = None) -> dict:
    solids = solids or build_all(project)
    cq = _cq()
    comp = cq.Compound.makeCompound(list(solids.values()))
    bb = comp.BoundingBox(tolerance=1e-6)
    return {"parts": len(solids), "overall_in": [round(bb.xlen, 3), round(bb.ylen, 3), round(bb.zlen, 3)],
            "volume_in3": round(sum(s.Volume() for s in solids.values()), 2),
            "all_valid": all(s.isValid() for s in solids.values()),
            "invalid": [n for n, s in solids.items() if not s.isValid()]}


def export(project: Project, fmt: str, path: str | Path, solids: dict | None = None) -> dict:
    """Write step | stl | brep. STEP keeps part names and material colours; units are millimetres."""
    cq = _cq()
    solids = solids or build_all(project)
    fmt = fmt.lower()
    path = Path(path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    mm = {n: s.scale(25.4) for n, s in solids.items()}
    if fmt == "step":
        assy = cq.Assembly(name=project.name.replace(" ", "_"))
        by = {b.name: b for b in project.boards}
        for n, s in mm.items():
            col = _hex_rgb(project.materials.get(by[n].material, {}).get("color", "#cccccc"))
            assy.add(s, name=n.replace(" ", "_"), color=cq.Color(*col))
        try:
            assy.export(str(path), exportType="STEP")
        except (AttributeError, TypeError):
            assy.save(str(path), exportType="STEP")
    elif fmt in ("stl", "brep"):
        comp = cq.Compound.makeCompound(list(mm.values()))
        if fmt == "stl":
            cq.exporters.export(cq.Workplane(obj=comp), str(path), exportType="STL", tolerance=0.05, angularTolerance=0.1)
        else:
            comp.exportBrep(str(path))
    else:
        raise ValueError("format must be step, stl or brep")
    return {"path": str(path), "bytes": path.stat().st_size}


# ------------------------------------------------------------------ shaded previews (numpy z-buffer, offscreen)
VIEWS = {"iso": ((1.0, -1.15, 0.85), (0, 0, 1)), "front": ((0, -1, 0), (0, 0, 1)), "back": ((0, 1, 0), (0, 0, 1)),
         "left": ((-1, 0, 0), (0, 0, 1)), "right": ((1, 0, 0), (0, 0, 1)), "top": ((0, 0, 1), (0, 1, 0)),
         "bottom": ((0, 0, -1), (0, -1, 0)), "iso_back": ((-1.0, 1.15, 0.85), (0, 0, 1))}


def tessellate_parts(solids: dict, colors: dict[str, str] | None = None, tol: float = 0.02) -> list[dict]:
    """[{name, rgb, tris (n,3,3)}] for every solid; the input of render_parts (and of the cad_run subprocess)."""
    import numpy as np

    parts = []
    for name, s in solids.items():
        verts, tr = s.tessellate(tol, 0.2)
        V = np.array([(v.x, v.y, v.z) for v in verts], dtype=float)
        T = V[np.array(tr, dtype=int)] if len(tr) else np.zeros((0, 3, 3))
        parts.append({"name": name, "rgb": _hex_rgb((colors or {}).get(name, "#c8c8c8")), "tris": T})
    return parts


def render_parts(parts: list[dict], view: str, path: str | Path, size: int = 900, edges: bool = True) -> str:
    """Flat-shaded orthographic image with a real depth buffer and part outlines (no GPU, no display needed).
    Good for checking shape; use Fusion's renderer (fusion_render) for photoreal output."""
    import numpy as np
    from PIL import Image

    if view not in VIEWS:
        raise ValueError(f"view must be one of {sorted(VIEWS)}")
    d, up = (np.array(v, float) for v in VIEWS[view])
    d /= np.linalg.norm(d)                         # from the model toward the camera
    right = np.cross(up, d)
    right /= np.linalg.norm(right)
    upv = np.cross(d, right)
    light = np.array([0.4, -0.6, 0.7])
    light /= np.linalg.norm(light)
    M = np.stack([right, upv, d])                  # world -> (screen x, screen y, depth)
    tris, cols, ids = [], [], []
    for pid, part in enumerate(parts):
        base = np.array(part["rgb"])
        T = part["tris"]
        if not len(T):
            continue
        n = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
        ln = np.linalg.norm(n, axis=1)
        ok = ln > 1e-12
        n = n[ok] / ln[ok][:, None]
        T = T[ok]
        front = n @ d >= -0.05                     # drop back-facing triangles
        n, T = n[front], T[front]
        shade = 0.5 + 0.5 * np.clip(n @ light, 0, None)
        S = T @ M.T
        for tri, sh_ in zip(S, shade):
            tris.append(tri)
            cols.append(base * sh_)
            ids.append(pid)
    if not tris:
        raise ValueError("nothing to draw: the model has no faces")
    T = np.array(tris)
    lo, hi = T[:, :, :2].reshape(-1, 2).min(0), T[:, :, :2].reshape(-1, 2).max(0)
    ss = 2
    N = size * ss
    scale = N * 0.88 / max(hi - lo)
    off = np.array([N / 2, N / 2]) - scale * (lo + hi) / 2
    zbuf = np.full((N, N), -np.inf)
    img = np.ones((N, N, 3))
    idb = np.full((N, N), -1, dtype=np.int32)
    for tri, col, pid in zip(T, cols, ids):
        px = tri[:, 0] * scale + off[0]
        py = N - (tri[:, 1] * scale + off[1])
        x0, x1 = int(max(np.floor(px.min()), 0)), int(min(np.ceil(px.max()), N - 1))
        y0, y1 = int(max(np.floor(py.min()), 0)), int(min(np.ceil(py.max()), N - 1))
        if x1 < x0 or y1 < y0:
            continue
        den = (py[1] - py[2]) * (px[0] - px[2]) + (px[2] - px[1]) * (py[0] - py[2])
        if abs(den) < 1e-12:
            continue
        gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        w0 = ((py[1] - py[2]) * (gx - px[2]) + (px[2] - px[1]) * (gy - py[2])) / den
        w1 = ((py[2] - py[0]) * (gx - px[2]) + (px[0] - px[2]) * (gy - py[2])) / den
        w2 = 1 - w0 - w1
        m = (w0 >= -1e-6) & (w1 >= -1e-6) & (w2 >= -1e-6)
        if not m.any():
            continue
        z = w0 * tri[0, 2] + w1 * tri[1, 2] + w2 * tri[2, 2]
        zs = zbuf[y0:y1 + 1, x0:x1 + 1]
        upd = m & (z > zs)
        zs[upd] = z[upd]
        img[y0:y1 + 1, x0:x1 + 1][upd] = col
        idb[y0:y1 + 1, x0:x1 + 1][upd] = pid
    if edges:
        e = np.zeros((N, N), bool)
        e[:, 1:] |= idb[:, 1:] != idb[:, :-1]
        e[1:, :] |= idb[1:, :] != idb[:-1, :]
        e2 = e.copy()
        e2[:, 1:] |= e[:, :-1]
        e2[1:, :] |= e[:-1, :]
        img[e2] = img[e2] * 0.45
    im = Image.fromarray((np.clip(img, 0, 1) * 255).astype("uint8")).resize((size, size), Image.LANCZOS)
    path = Path(path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path)
    return str(path)


def render_png(project: Project, view: str, path: str | Path, size: int = 900, solids: dict | None = None,
               edges: bool = True, parts: list[dict] | None = None) -> str:
    """Render a Project (pass `parts` from tessellate_parts to reuse one tessellation for several views)."""
    if parts is None:
        solids = solids or build_all(project)
        by = {b.name: b for b in project.boards}
        colors = {n: project.materials.get(by[n].material, {}).get("color", "#cccccc") for n in solids}
        parts = tessellate_parts(solids, colors)
    return render_parts(parts, view, path, size, edges)
