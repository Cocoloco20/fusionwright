"""fusionwright MCP server (stdio).

Two families of tools:
  fusion_*  drive a live Autodesk Fusion through the local FusionBridge add-in (loopback + token)
  wood_*    furniture design, cut lists, sheet nesting, drawings, STL/OBJ: pure Python, NO CAD needed
  cad_*     open-source CAD (CadQuery / OpenCascade): run any CadQuery code, exact STEP/STL, kernel checks, previews
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import Image, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from . import __version__
from .backends import cq as CQ
from .backends import fusion_scripts as S
from .backends.bridge import FusionBridge, FusionError
from .cabinet import build_cabinet
from .cutlist import board_feet, cutlist, sheet_area_sqft, to_csv, to_markdown
from .drawings import three_view_svg
from .meshout import skipped_cuts, to_obj, to_stl
from .model import Project
from .nesting import cut_lumber, nest_sheets, nest_sheets_svg

INSTRUCTIONS = """\
fusionwright builds real things (furniture, brackets, enclosures, anything solid) in Autodesk Fusion OR with no
Autodesk software at all (open-source CadQuery / OpenCascade).

Free route (no Fusion, no membership):
  cad_run(code)   -> write CadQuery code, get exact STEP + STL, volume/size/validity and preview images back.
  cad_preview / cad_check / cad_export work on the last cad_run result or the current wood_* project.
Fusion route (needs Fusion + the bridge add-in):
  fusion_api('ClassName') lists real API members (read it before writing code), then fusion_run(code).
Furniture projects (both routes):
1. wood_design_cabinet(...)  -> parametric design + cut list + sheet nesting + drawing + STL (+ STEP and previews when
   CadQuery is installed), all written to disk. open_deg=30 shows the lids hinged open.
2. cad_preview(['iso','front'])  -> see it without any CAD; cad_check() -> exact interference/validity check.
3. wood_build_in_fusion()    -> builds every part (arcs, cuts, hinge pose) as a named component in Fusion and verifies it.
4. fusion_look(['iso','front']) to SEE the Fusion result; fusion_check() to validate it. Fix with fusion_run(code).

Inside fusion_run: app, ui, design, root, adsk, P3, VI, FO, coll(), board(), IN (cm per inch) are predefined;
assign your answer to `result`. Fusion units are centimetres internally. fusion_run returns a checkpoint;
fusion_rollback(checkpoint) undoes everything after it.
Prefer one fusion_run per logical step and verify with fusion_inspect/fusion_look before continuing."""

mcp = MCPServer("fusionwright", instructions=INSTRUCTIONS, version=__version__)
bridge = FusionBridge()

READ = ToolAnnotations(readOnlyHint=True, openWorldHint=False)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False)
DESTRUCTIVE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=False)

HOME = Path(os.environ.get("FUSIONWRIGHT_HOME", "~/fusionwright-projects")).expanduser()
_current: dict[str, Any] = {"project": None, "dir": None}

_UNSAFE = re.compile(r"\b(subprocess|os\.system|os\.popen|shutil\.rmtree|os\.remove|os\.unlink|os\.rmdir|"
                     r"socket|urllib|requests|\.save\(|saveAs\(|saveDataVersion)\b|__import__\(['\"]os['\"]\)")


def _guard(code: str) -> None:
    if os.environ.get("FUSIONWRIGHT_UNSAFE") == "1":
        return
    m = _UNSAFE.search(code)
    if m:
        raise ToolError(
            f"Blocked: code uses '{m.group(0)}', which can delete files, reach the network or save to the cloud. "
            "Use the dedicated tools (fusion_export, wood_*) instead, or set FUSIONWRIGHT_UNSAFE=1 for the server "
            "if you really intend this. This is a safety net, not a sandbox.")


def _cap(obj: Any, limit: int = 9000) -> Any:
    s = json.dumps(obj, default=str)
    if len(s) <= limit:
        return obj
    return {"truncated": True, "preview": s[:limit], "hint": "Output was cut. Narrow the request (limit/detail) and retry."}


def _fusion(script: str, timeout: float = 95.0, **args) -> Any:
    try:
        return bridge.run(S.render(script, **args), timeout=timeout)["result"]
    except FusionError as e:
        raise ToolError(str(e))


# ------------------------------------------------------------------ Fusion tools
@mcp.tool(annotations=READ)
def fusion_status() -> dict:
    """Check that Fusion and the bridge add-in are reachable; report the active document."""
    try:
        ping = bridge.ping()
    except FusionError as e:
        raise ToolError(str(e))
    info = _fusion(S.INSPECT, detail="summary")
    return {"bridge": ping, "document": info["document"], "units": info["units"], "bodies": info["bodies"],
            "timeline_items": info["timeline_items"]}


@mcp.tool(annotations=READ)
def fusion_api(query: str, limit: int = 60) -> dict:
    """Look up the real Fusion API. Pass an exact class name (e.g. 'ExtrudeFeatureInput') to list its members with
    docs, or keywords (e.g. 'rectangular pattern') to find classes. Use this before writing fusion_run code."""
    return _cap(_fusion(S.API, query=query, limit=limit))


@mcp.tool(annotations=DESTRUCTIVE)
def fusion_run(code: str, label: str = "") -> dict:
    """Run Python inside Fusion's main thread (90 s limit). Predefined: app, ui, design, root, adsk, P3, VI, FO, IN,
    coll(), board(name,x,y,z,sx,sy,sz) in inches. Set `result` to return data. Returns a checkpoint you can pass to
    fusion_rollback. Dangerous operations (file deletion, network, cloud save) are blocked by default."""
    _guard(code)
    before = _fusion(S.COUNT)["timeline_items"]
    try:
        out = bridge.run(S.render(code), timeout=95.0)
    except FusionError as e:
        raise ToolError(f"{e}  (checkpoint {before}: fusion_rollback({before}) removes any partial changes)")
    return _cap({"result": out.get("result"), "stdout": (out.get("stdout") or "")[-1500:], "checkpoint": before,
                 "label": label})


@mcp.tool(annotations=DESTRUCTIVE)
def fusion_rollback(checkpoint: int) -> dict:
    """Delete every timeline item after `checkpoint` (a value returned by fusion_run)."""
    return _fusion(S.ROLLBACK, count=checkpoint)


@mcp.tool(annotations=READ)
def fusion_inspect(detail: str = "summary") -> dict:
    """Compact state of the active design: counts, overall size (in), volume, timeline problems, invalid bodies.
    detail='full' adds per-body boxes and user parameters."""
    return _cap(_fusion(S.INSPECT, detail=detail))


@mcp.tool(annotations=READ)
def fusion_check(expected_size_in: list[float] | None = None, tolerance_in: float = 0.01) -> dict:
    """Validate the design: body validity, timeline health, body-to-body interference (kernel), and optionally the
    overall X/Y/Z size in inches. Returns pass/fail plus the reasons."""
    info = _fusion(S.INSPECT, detail="summary")
    inter = _fusion(S.INTERFERENCE)
    problems = []
    if info["invalid_bodies"]:
        problems.append(f"invalid bodies: {info['invalid_bodies']}")
    if info["timeline_problems"]:
        problems.append(f"timeline problems: {info['timeline_problems'][:3]}")
    if inter.get("interferences"):
        problems.append(f"{inter['count']} interfering pairs, e.g. {inter['interferences'][:3]}")
    if expected_size_in and info["overall_size_in"]:
        for ax, (got, want) in zip("XYZ", zip(info["overall_size_in"], expected_size_in)):
            if abs(got - want) > tolerance_in:
                problems.append(f"{ax} size is {got} in, expected {want} in")
    return {"passed": not problems, "problems": problems, "bodies": info["bodies"],
            "overall_size_in": info["overall_size_in"]}


@mcp.tool(annotations=READ)
def fusion_look(views: list[str] | None = None, width: int = 900, height: int = 700) -> list[Image]:
    """Screenshot the active Fusion viewport from named views: iso, front, back, left, right, top, bottom."""
    views = views or ["iso"]
    bad = [v for v in views if v not in {"iso", "front", "back", "left", "right", "top", "bottom"}]
    if bad:
        raise ToolError(f"Unknown view(s) {bad}. Use iso, front, back, left, right, top or bottom.")
    paths = _fusion(S.LOOK, views=views, width=width, height=height)["paths"]
    return [Image(path=paths[v]) for v in views]


@mcp.tool(annotations=WRITE)
def fusion_render(quality: int = 25, width: int = 960, height: int = 720) -> list[Image]:
    """Photoreal render of the active design with Fusion's local renderer (quality 25-100; higher is slower)."""
    out = os.path.join(tempfile.mkdtemp(prefix="fw_render_"), "render.png")
    r = _fusion(S.RENDER, path=out, quality=quality, width=width, height=height, timeout=75)
    if not r["ok"]:
        raise ToolError(f"Render not finished after {r['seconds']} s (progress {r['progress']:.0%}). "
                        "Retry with quality=25 and a smaller width/height.")
    return [Image(path=out)]


@mcp.tool(annotations=WRITE)
def fusion_export(format: str, path: str = "") -> dict:
    """Export the active design to step, stl, f3d, obj, 3mf, iges or sat. Local file only (never the cloud)."""
    if not path:
        path = str(HOME / "exports" / f"design.{format.lower()}")
    return _fusion(S.EXPORT, format=format, path=str(Path(path).expanduser()))


@mcp.tool(annotations=DESTRUCTIVE)
def fusion_ui_command(id: str = "", search: str = "") -> dict:
    """Run any of Fusion's ~3,000 UI commands by id (what a menu click does), or search ids/names with `search`.
    Dialog commands stay open in Fusion until finished."""
    if not id and not search:
        raise ToolError("Pass id='Extrude' to run a command or search='extrude' to find command ids.")
    return _cap(_fusion(S.UI_COMMAND, id=id, search=search))


# ------------------------------------------------------------------ woodworking tools (no CAD needed)
def _save(project: Project, name: str | None = None) -> tuple[Path, dict]:
    d = HOME / re.sub(r"[^A-Za-z0-9_-]+", "_", (name or project.name).strip()).strip("_").lower()
    d.mkdir(parents=True, exist_ok=True)
    (d / "project.json").write_text(project.to_json())
    (d / "cutlist.md").write_text(to_markdown(project))
    (d / "cutlist.csv").write_text(to_csv(project))
    (d / "drawing_three_view.svg").write_text(three_view_svg(project))
    nest = nest_sheets(project)
    (d / "sheet_layout.svg").write_text(nest_sheets_svg(nest))
    (d / "model.obj").write_text(to_obj(project))
    engine = {"engine": "pure-python", "cuts_in_mesh": False, "skipped_cuts": skipped_cuts(project)}
    if CQ.available():                                   # exact solids, STEP with names/colours, previews
        solids = CQ.build_all(project)
        CQ.export(project, "step", d / "model.step", solids)
        CQ.export(project, "stl", d / "model.stl", solids)
        by = {b.name: b for b in project.boards}
        parts = CQ.tessellate_parts(solids, {n: project.materials.get(by[n].material, {}).get("color", "#ccc")
                                             for n in solids})
        for v in ("iso", "front", "top", "left"):
            CQ.render_png(project, v, d / f"preview_{v}.png", parts=parts)
        engine = {"engine": "cadquery", "cuts_in_mesh": True, "skipped_cuts": 0, **CQ.stats(project, solids),
                  "kernel_interferences": CQ.interferences(project, solids)}
        _cad_state.update(parts=parts, solids=solids, dir=d, label=project.name)
    else:
        (d / "model.stl").write_text(to_stl(project))
    _current.update(project=project, dir=d)
    return d, engine


def _project(path: str = "") -> Project:
    if path:
        p = Path(path).expanduser()
        p = p / "project.json" if p.is_dir() else p
        proj = Project.from_json(p.read_text())
        _current.update(project=proj, dir=p.parent)
        return proj
    if _current["project"] is None:
        raise ToolError("No project yet. Call wood_design_cabinet(...) first, or pass the path of a saved project.")
    return _current["project"]


@mcp.tool(annotations=WRITE)
def wood_design_cabinet(width: float = 24.0, depth: float = 22.5, tower_h: float = 24.0, step_h: float = 19.0,
                        center_h: float = 14.0, front_slats: int = 10, side_slats: int = 6, slat_gap: float = 0.15,
                        skin_t: float = 0.5, ply_t: float = 0.75, lid_t: float = 0.75, base_z: float = 3.25,
                        caster_h: float = 2.5, foot_arm: float = 4.5, arc_on_back: bool = True,
                        open_deg: float = 0.0, section_widths: list[float] | None = None,
                        name: str = "Rolling oak slat cabinet") -> dict:
    """Design the rolling oak-slat cabinet from the hand sketch (inches): vertical oak slats on four sides, a circular
    scoop cut through the slat tops, five hinged lids at 24/19/14 in, stepped plywood boxes with finger openings,
    and four L-shaped corner feet that hide swivel casters. open_deg shows the lids hinged open (try 30).
    Writes cut list, three-view drawing, sheet layout, STL, OBJ, project.json and, if CadQuery is installed, an exact
    STEP plus preview images."""
    try:
        p = build_cabinet(width=width, depth=depth, tower_h=tower_h, step_h=step_h, center_h=center_h,
                          front_slats=front_slats, side_slats=side_slats, slat_gap=slat_gap, skin_t=skin_t,
                          ply_t=ply_t, lid_t=lid_t, base_z=base_z, caster_h=caster_h, foot_arm=foot_arm,
                          arc_on_back=arc_on_back, open_deg=open_deg, section_widths=section_widths, name=name)
    except ValueError as e:
        raise ToolError(str(e))
    d, engine = _save(p)
    rows = cutlist(p)
    nest = nest_sheets(p)
    return {"project_dir": str(d), "parts": len(p.boards), "overall_in": [round(v, 3) for v in p.overall()],
            "solid_lumber": board_feet(rows), "plywood_sheets_4x8": nest["sheets"],
            "sheet_utilization_pct": nest["utilization_pct"], "box_interferences": len(p.interferences()),
            "interferences": len(engine.get("kernel_interferences", [])) + len(p.interferences()),
            "geometry": engine, "files": sorted(f.name for f in d.iterdir()), "notes": p.notes}


@mcp.tool(annotations=READ)
def wood_report(kind: str = "cutlist", project: str = "") -> Any:
    """Return a report for the current (or given) project: 'cutlist' (markdown), 'lumber' (1-D stock cutting plan),
    'sheets' (plywood nesting summary) or 'drawing' (path of the SVG)."""
    p = _project(project)
    if kind == "cutlist":
        return to_markdown(p)
    if kind == "lumber":
        return _cap(cut_lumber(p))
    if kind == "sheets":
        r = nest_sheets(p)
        return {k: r[k] for k in ("sheets", "utilization_pct", "sheet_w", "sheet_l", "kerf")} | {
            "layout_svg": str(Path(_current["dir"]) / "sheet_layout.svg")}
    if kind == "drawing":
        return {"svg": str(Path(_current["dir"]) / "drawing_three_view.svg")}
    raise ToolError("kind must be one of: cutlist, lumber, sheets, drawing")


@mcp.tool(annotations=WRITE)
def wood_build_in_fusion(project: str = "") -> dict:
    """Build the current (or given) project in the ACTIVE Fusion design: one named component per part with real arcs,
    cuts, cylinders and the hinge pose, oak / plywood / steel / rubber appearances, then verify size, validity and
    interference with Fusion's kernel. Parts that already exist (by name) are skipped, so it is safe to re-run."""
    p = _project(project)
    boards = [b.__dict__ for b in p.boards]
    terms = {"oak": ["oak"], "ply": ["birch", "plywood", "maple", "pine"], "steel": ["steel"],
             "rubber": ["rubber", "black"]}
    made = rotated = 0
    for start in range(0, len(boards), 12):
        r = _fusion(S.BUILD, boards=boards, start=start, end=start + 12, appearance_terms=terms)
        made += r["made"]
        rotated += r.get("rotated", 0)
    cuts = _fusion(S.CUTS, features=p.features)["finger_pulls_cut"] if p.features else []
    w, d, h = p.overall()
    check = fusion_check(expected_size_in=[w, d, h])
    return {"parts_built": made, "hinged_open": rotated, "finger_pulls": len(cuts), "verification": check}


# ------------------------------------------------------------------ open-source CAD tools (CadQuery, no Fusion)
_cad_state: dict[str, Any] = {"parts": None, "solids": None, "dir": None, "label": ""}
_CAD_UNSAFE = re.compile(r"\b(subprocess|os\.system|os\.popen|os\.remove|os\.unlink|os\.rmdir|shutil|socket|urllib|"
                         r"requests|http\.client|ctypes|importlib|pip)\b|__import__\(")


def _need_cq() -> None:
    if not CQ.available():
        raise ToolError(CQ.INSTALL_HINT)


@mcp.tool(annotations=WRITE)
def cad_status() -> dict:
    """Is the open-source CAD backend (CadQuery / OpenCascade) installed? Needs no Fusion and no account."""
    if not CQ.available():
        return {"available": False, "install": 'pip install "fusionwright[cad]"'}
    import cadquery as cq
    return {"available": True, "cadquery": getattr(cq, "__version__", "?"), "output_dir": str(HOME / "cad")}


@mcp.tool(annotations=WRITE)
def cad_run(code: str, label: str = "model", timeout_s: int = 90) -> list[str | Image]:
    """Run CadQuery Python and get the solid back: exact STEP + STL files, volume/size/validity, and iso/front/top
    previews. Predefined: `cq`, `OUT`. Assign `result` = a cq.Workplane / Shape / Assembly, a list, or a dict of
    name -> Workplane (each name becomes a coloured part). Use millimetres unless you need another unit.
    Example: result = cq.Workplane('XY').box(40, 30, 10).faces('>Z').workplane().hole(8)
    The code runs in a separate process with a time limit; obviously dangerous calls are blocked (safety net, not a
    sandbox)."""
    _need_cq()
    m = _CAD_UNSAFE.search(code)
    if m and os.environ.get("FUSIONWRIGHT_UNSAFE") != "1":
        raise ToolError(f"Blocked: code uses '{m.group(0)}'. CadQuery code should only build geometry. "
                        "Set FUSIONWRIGHT_UNSAFE=1 for the server if you really need this.")
    import numpy as np
    out = HOME / "cad" / (re.sub(r"[^A-Za-z0-9_-]+", "_", label).strip("_").lower() or "model")
    out.mkdir(parents=True, exist_ok=True)
    src = out / "code.py"
    src.write_text(code)
    try:
        subprocess.run([sys.executable, "-I", str(Path(__file__).parent / "backends" / "cq_runner.py"), str(src),
                        str(out)], capture_output=True, text=True, timeout=max(5, min(timeout_s, 300)))
    except subprocess.TimeoutExpired:
        raise ToolError(f"CadQuery code did not finish in {timeout_s} s. Simplify the model or raise timeout_s.")
    try:
        info = json.loads((out / "info.json").read_text())
    except Exception:
        raise ToolError("The CadQuery process produced no result. Check the code runs on its own.")
    if not info.get("ok"):
        raise ToolError(f"{info.get('error')}\n{info.get('trace', '')}")
    z = np.load(out / "mesh.npz")
    parts = [{"name": str(n), "rgb": tuple(z["rgb"][i]), "tris": z[f"t{i}"]} for i, n in enumerate(z["names"])]
    _cad_state.update(parts=parts, solids=None, dir=out, label=label)
    imgs = [Image(path=CQ.render_parts(parts, v, out / f"preview_{v}.png", 700)) for v in ("iso", "front", "top")]
    summary = {"overall": info["overall"], "parts": info["parts"], "all_valid": all(p["valid"] for p in info["parts"]),
               "files": {"step": str(out / "model.step"), "stl": str(out / "model.stl"), "code": str(src)}}
    return [json.dumps(summary), *imgs]


@mcp.tool(annotations=READ)
def cad_preview(views: list[str] | None = None, size: int = 800) -> list[Image]:
    """Shaded previews (iso, front, back, left, right, top, bottom, iso_back) of the last cad_run result or of the
    current wood_* project, with no CAD application needed."""
    views = views or ["iso"]
    bad = [v for v in views if v not in CQ.VIEWS]
    if bad:
        raise ToolError(f"Unknown view(s) {bad}. Use {', '.join(sorted(CQ.VIEWS))}.")
    if _cad_state["parts"] is None:
        _need_cq()
        if _current["project"] is None:
            raise ToolError("Nothing to preview yet. Run cad_run(code) or wood_design_cabinet(...) first.")
        p = _current["project"]
        solids = CQ.build_all(p)
        by = {b.name: b for b in p.boards}
        _cad_state["parts"] = CQ.tessellate_parts(solids, {n: p.materials.get(by[n].material, {}).get("color", "#ccc")
                                                         for n in solids})
    out = Path(_cad_state["dir"] or tempfile.mkdtemp(prefix="fw_cad_"))
    return [Image(path=CQ.render_parts(_cad_state["parts"], v, out / f"preview_{v}.png", size)) for v in views]


@mcp.tool(annotations=READ)
def cad_check(expected_size_in: list[float] | None = None, tolerance_in: float = 0.01) -> dict:
    """Exact check of the current wood_* project with the open-source kernel: every part valid, no overlapping
    solids (boolean intersection), and optionally the overall X/Y/Z size in inches."""
    _need_cq()
    p = _project()
    solids = CQ.build_all(p)
    st = CQ.stats(p, solids)
    inter = CQ.interferences(p, solids)
    problems = []
    if st["invalid"]:
        problems.append(f"invalid solids: {st['invalid'][:5]}")
    if inter:
        problems.append(f"{len(inter)} overlapping pairs, e.g. {inter[:3]}")
    if expected_size_in:
        for ax, got, want in zip("XYZ", st["overall_in"], expected_size_in):
            if abs(got - want) > tolerance_in:
                problems.append(f"{ax} size is {got} in, expected {want} in")
    return {"passed": not problems, "problems": problems, **st}


@mcp.tool(annotations=WRITE)
def cad_export(format: str = "step", path: str = "") -> dict:
    """Write the current wood_* project with the open-source kernel: step (names + colours), stl or brep, millimetres."""
    _need_cq()
    p = _project()
    path = path or str((_current["dir"] or HOME) / f"model.{format.lower()}")
    try:
        return CQ.export(p, format, path)
    except ValueError as e:
        raise ToolError(str(e))


def main() -> None:
    mcp.run("stdio")


if __name__ == "__main__":
    main()
