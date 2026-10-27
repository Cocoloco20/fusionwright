"""Live tests against a running Fusion with the FusionBridge add-in. Skipped automatically when Fusion is
not reachable. Every test works in a scratch document that is closed WITHOUT saving (nothing is written
to the Autodesk cloud).

    pytest tests/integration -q
"""
import json
import os
import tempfile

import pytest

from fusionwright.backends import fusion_scripts as S
from fusionwright.backends.bridge import FusionBridge, FusionError

bridge = FusionBridge()
try:
    bridge.ping()
    LIVE = True
except FusionError:
    LIVE = False

pytestmark = pytest.mark.skipif(not LIVE, reason="Fusion bridge not running")

NEW_DOC = "doc = app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType); result = doc.name"
CLOSE_DOC = "app.activeDocument.close(False); result = 'closed'"


def run(script, **args):
    return bridge.run(S.render(script, **args))["result"]


@pytest.fixture()
def scratch():
    bridge.run(NEW_DOC)
    try:
        yield
    finally:
        try:
            bridge.run(CLOSE_DOC)
        except FusionError:
            pass


BRACKET = """
sk = root.sketches.add(root.xYConstructionPlane)
sk.sketchCurves.sketchLines.addTwoPointRectangle(P3(0, 0, 0), P3(8 * IN, 4 * IN, 0))
ext = root.features.extrudeFeatures.addSimple(sk.profiles.item(0), VI.createByReal(1 * IN), FO.NewBodyFeatureOperation)
ext.bodies.item(0).name = 'Plate'
board('Block', 1, 1, 1, 2, 2, 2)
result = 1
"""


def test_build_part_and_verify(scratch):
    run(BRACKET)
    info = run(S.INSPECT, detail="summary")
    assert info["bodies"] == 2
    assert not info["invalid_bodies"] and not info["timeline_problems"]
    w, d, h = info["overall_size_in"]
    assert (round(w, 2), round(d, 2), round(h, 2)) == (8.0, 4.0, 3.0)
    assert abs(info["total_volume_in3"] - (8 * 4 * 1 + 2 * 2 * 2)) < 1e-3
    assert run(S.INTERFERENCE)["interferences"] == []


def test_look_export_render(scratch):
    run(BRACKET)
    paths = run(S.LOOK, views=["iso", "front", "top", "right"], width=600, height=450)["paths"]
    assert all(os.path.getsize(v) > 2000 for v in paths.values())
    import hashlib
    digests = {k: hashlib.md5(open(v, "rb").read()).hexdigest() for k, v in paths.items()}
    assert len(set(digests.values())) == len(digests), "views must differ: " + str(digests)
    d = tempfile.mkdtemp(prefix="fw_it_")
    for fmt in ("step", "stl", "f3d", "obj", "3mf"):
        out = run(S.EXPORT, format=fmt, path=os.path.join(d, "part." + fmt))
        assert out["bytes"] > 500, (fmt, out)
    r = run(S.RENDER, path=os.path.join(d, "r.png"), quality=15, width=480, height=360, timeout=60)
    assert r["ok"], r


def test_api_lookup():
    r = run(S.API, query="ExtrudeFeatureInput")
    assert r["class"].endswith("ExtrudeFeatureInput") and any(m["name"] == "setDistanceExtent" for m in r["members"])
    r2 = run(S.API, query="rectangular pattern")
    assert any("RectangularPattern" in c for c in r2["matching_classes"])


def test_checkpoint_and_rollback(scratch):
    n0 = run(S.COUNT)["timeline_items"]
    run("board('a', 0, 0, 0, 2, 2, 2)\nboard('b', 5, 0, 0, 2, 2, 2)\nresult = 1")
    assert run(S.COUNT)["timeline_items"] > n0
    r = run(S.ROLLBACK, count=n0)
    assert r["timeline_items"] == n0
    assert run(S.INSPECT)["bodies"] == 0


def test_ui_command_search():
    r = run(S.UI_COMMAND, search="extrude")
    assert any(m["id"] == "Extrude" for m in r["matches"])
