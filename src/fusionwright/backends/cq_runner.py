"""Runs user CadQuery code in a separate process (started by the cad_run tool, never imported by the server).

usage: python -I cq_runner.py CODE_FILE OUT_DIR

The code sees `cq` (cadquery) and `OUT` (output directory) and must assign `result` to one of: a cq.Workplane, a
cq.Shape, a cq.Assembly, a list of those, or a dict of name -> Workplane/Shape. Units are whatever the code uses;
STEP/STL are written as-is (use millimetres if the file is going to a slicer or another CAD tool).
Writes model.step, model.stl, mesh.npz (for previews) and info.json to OUT_DIR.
"""
import json
import sys
import traceback
from pathlib import Path

PALETTE = ["#c8a46a", "#8a8f94", "#6b8cae", "#b5654f", "#7fa66a", "#a98bc2", "#d1b24c", "#5d5d63"]


def _shapes(result):
    import cadquery as cq

    def one(x):
        if isinstance(x, cq.Workplane):
            return [v for v in x.vals() if isinstance(v, cq.Shape)]
        if isinstance(x, cq.Shape):
            return [x]
        raise TypeError(f"cannot use a {type(x).__name__} as a solid; return Workplane, Shape, Assembly, a list or a dict")

    if isinstance(result, cq.Assembly):
        return {"assembly": [result.toCompound()]}
    if isinstance(result, dict):
        return {str(k): one(v) for k, v in result.items()}
    if isinstance(result, (list, tuple)):
        return {f"part_{i + 1}": one(v) for i, v in enumerate(result)}
    return {"part": one(result)}


def _save_step(assy, path):
    try:
        assy.export(str(path), exportType="STEP")
    except (AttributeError, TypeError):
        assy.save(str(path), exportType="STEP")


def main(code_file: str, out_dir: str) -> int:
    import cadquery as cq
    import numpy as np

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    ns = {"cq": cq, "OUT": str(out), "__name__": "__cad__"}
    try:
        exec(compile(Path(code_file).read_text(), "cad_code", "exec"), ns)
        if "result" not in ns:
            raise ValueError("The code must assign its answer to `result` (a Workplane, Shape, Assembly, list or dict).")
        groups = _shapes(ns["result"])
        parts, solids, info = [], {}, []
        for gi, (name, shapes) in enumerate(groups.items()):
            comp = cq.Compound.makeCompound(shapes)
            solids[name] = comp
            verts, tr = comp.tessellate(0.05 * max(comp.BoundingBox(tolerance=1e-6).DiagonalLength / 100, 0.2), 0.2)
            V = np.array([(v.x, v.y, v.z) for v in verts], dtype=float)
            T = V[np.array(tr, dtype=int)] if len(tr) else np.zeros((0, 3, 3))
            h = PALETTE[gi % len(PALETTE)].lstrip("#")
            parts.append((name, [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)], T))
            bb = comp.BoundingBox(tolerance=1e-6)
            info.append({"name": name, "volume": round(comp.Volume(), 4), "valid": bool(comp.isValid()),
                         "solids": len(comp.Solids()), "size": [round(bb.xlen, 4), round(bb.ylen, 4), round(bb.zlen, 4)]})
        whole = cq.Compound.makeCompound(list(solids.values()))
        cq.exporters.export(cq.Workplane(obj=whole), str(out / "model.stl"), exportType="STL", tolerance=0.05,
                            angularTolerance=0.1)
        assy = cq.Assembly(name="model")
        for gi, (name, comp) in enumerate(solids.items()):
            h = PALETTE[gi % len(PALETTE)].lstrip("#")
            assy.add(comp, name=name.replace(" ", "_"),
                     color=cq.Color(*[int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]))
        _save_step(assy, out / "model.step")
        np.savez_compressed(out / "mesh.npz", names=np.array([p[0] for p in parts]),
                            rgb=np.array([p[1] for p in parts]),
                            **{f"t{i}": p[2] for i, p in enumerate(parts)})
        bb = whole.BoundingBox(tolerance=1e-6)
        (out / "info.json").write_text(json.dumps({
            "ok": True, "parts": info, "overall": [round(bb.xlen, 4), round(bb.ylen, 4), round(bb.zlen, 4)],
            "min": [round(bb.xmin, 4), round(bb.ymin, 4), round(bb.zmin, 4)]}))
        return 0
    except Exception as e:                                                   # report, never crash silently
        (out / "info.json").write_text(json.dumps({"ok": False, "error": f"{type(e).__name__}: {e}",
                                                  "trace": traceback.format_exc()[-1800:]}))
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
