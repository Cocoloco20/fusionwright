"""End-to-end over real stdio: spawn the server as a subprocess and talk MCP to it (no Fusion needed)."""
import asyncio
import json
import os
import sys

from mcp.client import Client
from mcp.client.stdio import StdioServerParameters


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
                    "wood_build_in_fusion", "wood_report"} <= names
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
