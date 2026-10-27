"""Full MCP round trip with a live Fusion: client -> stdio server -> bridge -> Fusion kernel -> image back."""
import asyncio
import json
import os
import sys

import pytest
from mcp.client import Client
from mcp.client.stdio import StdioServerParameters

from fusionwright.backends.bridge import FusionBridge, FusionError

bridge = FusionBridge()
try:
    bridge.ping()
    LIVE = True
except FusionError:
    LIVE = False
pytestmark = pytest.mark.skipif(not LIVE, reason="Fusion bridge not running")


def _text(res):
    return "".join(getattr(c, "text", "") for c in res.content)


def test_design_build_look_check_roundtrip(tmp_path):
    bridge.run("app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType); result = 1")
    env = dict(os.environ, FUSIONWRIGHT_HOME=str(tmp_path))
    params = StdioServerParameters(command=sys.executable, args=["-m", "fusionwright"], env=env)

    async def go():
        async with Client(params) as c:
            st = json.loads(_text(await c.call_tool("fusion_status", {})))
            assert st["bridge"]["ok"] if isinstance(st["bridge"], dict) and "ok" in st["bridge"] else True
            d = await c.call_tool("wood_design_cabinet", {})
            assert not d.is_error
            b = await c.call_tool("wood_build_in_fusion", {})
            assert not b.is_error, _text(b)
            out = json.loads(_text(b))
            assert out["verification"]["passed"], out
            assert out["finger_pulls"] == 5
            look = await c.call_tool("fusion_look", {"views": ["iso", "front"], "width": 600, "height": 450})
            imgs = [x for x in look.content if getattr(x, "type", "") == "image"]
            assert len(imgs) == 2
            # an actionable error comes back as a tool error, not a crash
            bad = await c.call_tool("fusion_run", {"code": "raise ValueError('boom')"})
            assert bad.is_error and "boom" in _text(bad) and "fusion_rollback" in _text(bad)
    try:
        asyncio.run(go())
    finally:
        bridge.run("app.activeDocument.close(False); result = 1")
