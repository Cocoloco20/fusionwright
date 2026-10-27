"""fusionwright MCP server (stdio): lets an AI assistant drive a live Autodesk Fusion through the local
FusionBridge add-in (loopback + token). Look up the real API, run Python in Fusion, see the model, verify it with
Fusion's kernel, render it, export it, roll back mistakes, run any UI command."""
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

INSTRUCTIONS = """\
fusionwright lets you build and edit anything in the user's live Autodesk Fusion: parts, assemblies, enclosures,
brackets, furniture, jigs, product mock-ups, anything solid.

Work in small verified steps:
1. fusion_status() to confirm Fusion is reachable and see the active document.
2. fusion_api('ClassName') lists the REAL API members (read it before writing code; do not guess method names).
3. fusion_run(code) does one logical step (a sketch and extrude, a pattern, a fillet...). It returns a checkpoint.
4. fusion_look(['iso','front']) to SEE the result and fusion_inspect()/fusion_check() to measure it against the
   arithmetic (sizes, volume, invalid bodies, interference). Fix mistakes, or fusion_rollback(checkpoint).
5. fusion_render() for a photoreal image, fusion_export('step'|'stl'|'f3d'|'obj'|'3mf'|'iges'|'sat') to hand over files.
fusion_ui_command(search='extrude') finds and runs any of Fusion's ~3,000 UI commands.

Inside fusion_run: app, ui, design, root, adsk, P3 (=Point3D.create), VI (ValueInput), FO (FeatureOperations),
coll(), board(name,x,y,z,sx,sy,sz) (a box in inches), IN (cm per inch) are predefined; assign your answer to
`result`. Fusion units are centimetres internally. Prefer one fusion_run per logical step."""

mcp = MCPServer("fusionwright", instructions=INSTRUCTIONS, version=__version__)
bridge = FusionBridge()

READ = ToolAnnotations(readOnlyHint=True, openWorldHint=False)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False)
DESTRUCTIVE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=False)

HOME = Path(os.environ.get("FUSIONWRIGHT_HOME", "~/fusionwright-projects")).expanduser()

_UNSAFE = re.compile(r"\b(?:subprocess|os\.system|os\.popen|shutil\.rmtree|os\.remove|os\.unlink|os\.rmdir|socket|urllib|requests)\b"
                     r"|\.save\(|\.saveAs\(|saveDataVersion|__import__\(['\"]os['\"]\)")


def _guard(code: str) -> None:
    if os.environ.get("FUSIONWRIGHT_UNSAFE") == "1":
        return
    m = _UNSAFE.search(code)
    if m:
        raise ToolError(
            f"Blocked: code uses '{m.group(0)}', which can delete files, reach the network or save to the cloud. "
            "Use the dedicated tools (fusion_export) instead, or set FUSIONWRIGHT_UNSAFE=1 for the server "
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


def main() -> None:
    mcp.run("stdio")


if __name__ == "__main__":
    main()
