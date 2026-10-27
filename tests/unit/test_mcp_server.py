"""End-to-end over real stdio: spawn the server as a subprocess and talk MCP to it (no Fusion needed)."""
import asyncio
import os
import sys

from mcp.client import Client
from mcp.client.stdio import StdioServerParameters

TOOLS = {"fusion_status", "fusion_api", "fusion_run", "fusion_rollback", "fusion_inspect", "fusion_check",
         "fusion_look", "fusion_render", "fusion_export", "fusion_ui_command"}


def _params(tmp):
    env = dict(os.environ, FUSIONWRIGHT_HOME=str(tmp), FUSIONWRIGHT_URL="http://127.0.0.1:1")   # nothing listens there
    return StdioServerParameters(command=sys.executable, args=["-m", "fusionwright"], env=env)


def _text(res):
    return "".join(getattr(c, "text", "") for c in res.content)


def test_tools_listed_with_annotations_and_instructions(tmp_path):
    async def go():
        async with Client(_params(tmp_path)) as c:
            tools = (await c.list_tools()).tools
            names = {t.name for t in tools}
            assert names == TOOLS
            by = {t.name: t for t in tools}
            assert by["fusion_inspect"].annotations.read_only_hint is True
            assert by["fusion_run"].annotations.destructive_hint is True
            assert "fusion_api" in (c.instructions or "")
    asyncio.run(go())


def test_dangerous_code_is_blocked_before_reaching_fusion(tmp_path):
    async def go():
        async with Client(_params(tmp_path)) as c:
            for code in ("import shutil; shutil.rmtree('/')", "import subprocess; subprocess.run(['ls'])",
                         "design.saveAs('x', None, '', '')"):
                r = await c.call_tool("fusion_run", {"code": code})
                assert r.is_error and "Blocked" in _text(r), code
    asyncio.run(go())


def test_unknown_view_is_explained(tmp_path):
    async def go():
        async with Client(_params(tmp_path)) as c:
            r = await c.call_tool("fusion_look", {"views": ["sideways"]})
            assert r.is_error and "Unknown view" in _text(r)
    asyncio.run(go())


def test_fusion_not_running_gives_an_actionable_error(tmp_path):
    async def go():
        async with Client(_params(tmp_path)) as c:
            r = await c.call_tool("fusion_status", {})
            assert r.is_error and _text(r)
    asyncio.run(go())
