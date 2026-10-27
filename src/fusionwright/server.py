"""fusionwright MCP server (stdio).

Two families of tools:
  fusion_*  drive a live Autodesk Fusion through the local FusionBridge add-in (loopback + token)
  wood_*    furniture design, cut lists, sheet nesting, drawings, STL/OBJ: pure Python, NO CAD needed
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import Image, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from . import __version__
from .backends import fusion_scripts as S
from .backends.bridge import FusionBridge, FusionError
from .cabinet import build_cabinet
from .cutlist import board_feet, cutlist, sheet_area_sqft, to_csv, to_markdown
from .drawings import three_view_svg
from .meshout import to_obj, to_stl
from .model import Project
from .nesting import cut_lumber, nest_sheets, nest_sheets_svg

INSTRUCTIONS = """\
fusionwright builds real furniture projects, in Autodesk Fusion or with no CAD at all.

Typical flow:
1. wood_design_cabinet(...)  -> parametric design + cut list + sheet nesting + drawing + STL, all written to disk.
2. wood_build_in_fusion()    -> builds every board as a named component in the open Fusion document and verifies it.
3. fusion_look(['iso','front']) to SEE the result; fusion_check() to validate it. Fix with fusion_run(code).

Free-form CAD: fusion_api('ClassName') lists real API members (read it before writing code), then fusion_run(code).
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
def _save(project: Project, name: str | None = None) -> Path:
    d = HOME / re.sub(r"[^A-Za-z0-9_-]+", "_", (name or project.name).strip()).strip("_").lower()
    d.mkdir(parents=True, exist_ok=True)
    (d / "project.json").write_text(project.to_json())
    (d / "cutlist.md").write_text(to_markdown(project))
    (d / "cutlist.csv").write_text(to_csv(project))
    (d / "drawing_three_view.svg").write_text(three_view_svg(project))
    nest = nest_sheets(project)
    (d / "sheet_layout.svg").write_text(nest_sheets_svg(nest))
    (d / "model.stl").write_text(to_stl(project))
    (d / "model.obj").write_text(to_obj(project))
    _current.update(project=project, dir=d)
    return d


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
                        center_h: float = 14.0, slat_w: float = 1.5, slat_t: float = 0.75, slat_gap: float = 0.5,
                        ply_t: float = 0.75, lid_t: float = 0.75, base_z: float = 3.0, caster_h: float = 2.5,
                        name: str = "Rolling oak slat cabinet") -> dict:
    """Design the parametric rolling oak-slat cabinet (stepped hinged lids, plywood carcass, caster blocks). Inches.
    Writes cut list (md/csv), three-view drawing (svg), sheet layout (svg), STL, OBJ and project.json to disk."""
    try:
        p = build_cabinet(width=width, depth=depth, tower_h=tower_h, step_h=step_h, center_h=center_h, slat_w=slat_w,
                          slat_t=slat_t, slat_gap=slat_gap, ply_t=ply_t, lid_t=lid_t, base_z=base_z,
                          caster_h=caster_h, name=name)
    except ValueError as e:
        raise ToolError(str(e))
    d = _save(p)
    rows = cutlist(p)
    nest = nest_sheets(p)
    return {"project_dir": str(d), "boards": len(p.boards), "overall_in": [round(v, 3) for v in p.overall()],
            "solid_lumber": board_feet(rows), "plywood_sheets_4x8": nest["sheets"],
            "sheet_utilization_pct": nest["utilization_pct"], "interferences": len(p.interferences()),
            "files": sorted(f.name for f in d.iterdir()), "notes": p.notes}


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
    """Build the current (or given) project in the ACTIVE Fusion design: one named component per board with oak /
    plywood appearances and finger-pull cuts, then verify size, validity and interference with the kernel."""
    p = _project(project)
    boards = [b.__dict__ for b in p.boards]
    terms = {"oak": ["oak"], "ply": ["birch", "plywood", "maple", "pine"]}
    made = 0
    for start in range(0, len(boards), 20):
        made += _fusion(S.BUILD, boards=boards, start=start, end=start + 20, appearance_terms=terms)["made"]
    cuts = _fusion(S.CUTS, features=p.features)
    w, d, h = p.overall()
    check = fusion_check(expected_size_in=[w, d, h])
    return {"boards_built": made, "finger_pulls": len(cuts["finger_pulls_cut"]), "verification": check}


def main() -> None:
    mcp.run("stdio")


if __name__ == "__main__":
    main()
