"""End-to-end over real stdio: spawn the server as a subprocess and talk MCP to it (no Fusion needed)."""
import asyncio
import json
import os
import sys

import pytest
from mcp.client import Client
from mcp.client.stdio import StdioServerParameters


try:
    import cadquery  # noqa: F401
    HAS_CQ = True
except ImportError:
    HAS_CQ = False
needs_cq = pytest.mark.skipif(not HAS_CQ, reason="CadQuery not installed (pip install 'fusionwright[cad]')")


def _params(tmp):
    env = dict(os.environ, FUSIONWRIGHT_HOME=str(tmp))
    return StdioServerParameters(command=sys.executable, args=["-m", "fusionwright"], env=env)


def _text(res):
    return "".join(getattr(c, "text", "") for c in res.content)


def test_tools_listed_with_annotations_and_instructions(tmp_path):
    async def go():
        async with Client(_params(tmp_path)) as c:
            tools = (await c.list_tools()).tools
            names = {t.name for t in tools}
            assert {"fusion_status", "fusion_api", "fusion_run", "fusion_look", "fusion_check", "wood_design_cabinet",
                    "wood_build_in_fusion", "wood_report", "cad_run", "cad_preview", "cad_check", "cad_export",
                    "cad_status"} <= names
            by = {t.name: t for t in tools}
            assert by["fusion_inspect"].annotations.read_only_hint is True
            assert by["fusion_run"].annotations.destructive_hint is True
            assert "wood_design_cabinet" in (c.instructions or "")
            assert len(names) <= 20          # small surface on purpose
    asyncio.run(go())


def test_design_cabinet_without_any_cad(tmp_path):
    async def go():
        async with Client(_params(tmp_path)) as c:
            r = await c.call_tool("wood_design_cabinet", {})
            assert not r.is_error, _text(r)
            data = json.loads(_text(r))
            assert data["overall_in"] == [24.0, 22.5, 24.0] and data["interferences"] == 0
            files = set(data["files"])
            assert {"cutlist.md", "cutlist.csv", "drawing_three_view.svg", "sheet_layout.svg", "model.stl",
                    "model.obj", "project.json"} <= files
            if HAS_CQ:
                assert {"model.step", "preview_iso.png", "preview_front.png"} <= files
                assert data["geometry"]["all_valid"] is True
            md = await c.call_tool("wood_report", {"kind": "cutlist"})
            assert "board feet" in _text(md)
    asyncio.run(go())


def test_bad_parameters_return_fixable_error(tmp_path):
    async def go():
        async with Client(_params(tmp_path)) as c:
            r = await c.call_tool("wood_design_cabinet", {"center_h": 40})
            assert r.is_error and "Heights" in _text(r)
    asyncio.run(go())


def test_dangerous_code_is_blocked_before_reaching_fusion(tmp_path):
    async def go():
        async with Client(_params(tmp_path)) as c:
            r = await c.call_tool("fusion_run", {"code": "import shutil; shutil.rmtree('/')"})
            assert r.is_error and "Blocked" in _text(r)
    asyncio.run(go())


@needs_cq
def test_cad_run_builds_exports_and_previews_without_fusion(tmp_path):
    code = "result = {'base': cq.Workplane('XY').box(40, 30, 10).faces('>Z').workplane().hole(8)}"

    async def go():
        async with Client(_params(tmp_path)) as c:
            r = await c.call_tool("cad_run", {"code": code, "label": "bracket"})
            assert not r.is_error, _text(r)
            info = json.loads(_text(r))
            assert info["all_valid"] and info["overall"][0] == 40.0
            assert any(getattr(x, "type", "") == "image" for x in r.content)          # previews came back
            assert (tmp_path / "cad" / "bracket" / "model.step").stat().st_size > 1000
            assert (tmp_path / "cad" / "bracket" / "model.stl").stat().st_size > 1000
            p = await c.call_tool("cad_preview", {"views": ["top"]})
            assert not p.is_error
    asyncio.run(go())


@needs_cq
def test_cad_run_reports_code_errors_and_blocks_danger(tmp_path):
    async def go():
        async with Client(_params(tmp_path)) as c:
            bad = await c.call_tool("cad_run", {"code": "result = 1 / 0"})
            assert bad.is_error and "ZeroDivisionError" in _text(bad)
            none = await c.call_tool("cad_run", {"code": "x = 1"})
            assert none.is_error and "result" in _text(none)
            blocked = await c.call_tool("cad_run", {"code": "import subprocess; subprocess.run(['ls'])"})
            assert blocked.is_error and "Blocked" in _text(blocked)
    asyncio.run(go())


@needs_cq
def test_cad_check_and_export_on_the_cabinet(tmp_path):
    async def go():
        async with Client(_params(tmp_path)) as c:
            await c.call_tool("wood_design_cabinet", {"open_deg": 30})
            chk = await c.call_tool("cad_check", {})
            data = json.loads(_text(chk))
            assert data["parts"] == 99 and data["all_valid"] is True and data["problems"] == []
            tall = json.loads(_text(await c.call_tool("cad_check", {"expected_size_in": [24, 22.5, 24]})))
            assert tall["passed"] is False and "Z size" in tall["problems"][0]      # open lids rise above 24 in
            ex = await c.call_tool("cad_export", {"format": "step"})
            assert not ex.is_error and json.loads(_text(ex))["bytes"] > 10000
    asyncio.run(go())
