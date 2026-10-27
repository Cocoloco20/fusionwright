#!/usr/bin/env python3
"""Capability tests for the Fusion bridge.

Every test runs INSIDE Fusion (through the bridge) in a fresh scratch document that is
closed afterwards without saving. Nothing is written to the user's Autodesk cloud.
Fusion's internal length unit is centimetres, so all sizes below are in cm.

Usage:  python3 run_tests.py            # run everything
        python3 run_tests.py loft hole  # run tests whose name contains any of these words
"""
import json
import os
import sys
import textwrap
import time
import urllib.error
import urllib.request

URL = 'http://127.0.0.1:8765/eval'
TOKEN = open(os.path.expanduser('~/.fusion-bridge-token')).read().strip()


def call(code, timeout=150):
    req = urllib.request.Request(
        URL, data=json.dumps({'code': code}).encode(),
        headers={'Authorization': 'Bearer ' + TOKEN, 'Content-Type': 'application/json'})
    try:
        return json.loads(urllib.request.urlopen(req, timeout=timeout).read())
    except urllib.error.HTTPError as e:
        return {'ok': False, 'error': 'HTTP %s: %s' % (e.code, e.read().decode())}
    except Exception as e:  # noqa
        return {'ok': False, 'error': repr(e)}


PRE = """
import tempfile, os, math, shutil
doc = app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
design = adsk.fusion.Design.cast(doc.products.itemByProductType('DesignProductType'))
design.designType = adsk.fusion.DesignTypes.ParametricDesignType
root = design.rootComponent
P3 = adsk.core.Point3D.create
VI = adsk.core.ValueInput
FO = adsk.fusion.FeatureOperations

def box(comp, w, d, h, plane=None, x0=0, y0=0):
    sk = comp.sketches.add(plane or comp.xYConstructionPlane)
    sk.sketchCurves.sketchLines.addTwoPointRectangle(P3(x0, y0, 0), P3(x0 + w, y0 + d, 0))
    inp = comp.features.extrudeFeatures.createInput(sk.profiles.item(0), FO.NewBodyFeatureOperation)
    inp.setDistanceExtent(False, VI.createByReal(h))
    return comp.features.extrudeFeatures.add(inp)

def coll(*items):
    c = adsk.core.ObjectCollection.create()
    for i in items:
        c.add(i)
    return c
"""

TESTS = []


def test(name):
    def deco(body):
        TESTS.append((name, body))
        return body
    return deco


test('env')(r'''
result = {'version': app.version, 'units': design.unitsManager.defaultLengthUnits,
          'designType': str(design.designType)}
''')

test('sketch + extrude (volume check)')(r'''
f = box(root, 10, 5, 2)
v = f.bodies.item(0).physicalProperties.volume
assert abs(v - 100) < 1e-6, v
result = {'volume_cm3': v}
''')

test('sketch constraints + driven dimension')(r'''
sk = root.sketches.add(root.xYConstructionPlane)
ln = sk.sketchCurves.sketchLines.addByTwoPoints(P3(0, 0, 0), P3(3, 1, 0))
sk.geometricConstraints.addHorizontal(ln)
dim = sk.sketchDimensions.addDistanceDimension(
    ln.startSketchPoint, ln.endSketchPoint,
    adsk.fusion.DimensionOrientations.AlignedDimensionOrientation, P3(1.5, -1, 0))
dim.parameter.value = 5.0
assert abs(ln.length - 5.0) < 1e-6, ln.length
assert abs(ln.startSketchPoint.geometry.y - ln.endSketchPoint.geometry.y) < 1e-6
result = {'length': ln.length, 'constraints': sk.geometricConstraints.count}
''')

test('extrude cut into a face')(r'''
f = box(root, 10, 10, 2)
b = f.bodies.item(0)
v0 = b.physicalProperties.volume
top = max(b.faces, key=lambda fc: fc.centroid.z)
sk = root.sketches.add(top)
sk.sketchCurves.sketchCircles.addByCenterRadius(sk.modelToSketchSpace(top.centroid), 1.0)
prof = min(sk.profiles, key=lambda pr: pr.areaProperties().area)
inp = root.features.extrudeFeatures.createInput(prof, FO.CutFeatureOperation)
dist = adsk.fusion.DistanceExtentDefinition.create(VI.createByReal(1.0))
inp.setOneSideExtent(dist, adsk.fusion.ExtentDirections.NegativeExtentDirection)
root.features.extrudeFeatures.add(inp)
v1 = root.bRepBodies.item(0).physicalProperties.volume
assert abs((v0 - v1) - math.pi) < 1e-3, (v0, v1)
result = {'removed_cm3': v0 - v1}
''')

test('revolve')(r'''
sk = root.sketches.add(root.xYConstructionPlane)
sk.sketchCurves.sketchLines.addTwoPointRectangle(P3(1, 0, 0), P3(2, 3, 0))
inp = root.features.revolveFeatures.createInput(sk.profiles.item(0), root.yConstructionAxis, FO.NewBodyFeatureOperation)
inp.setAngleExtent(False, VI.createByString('360 deg'))
f = root.features.revolveFeatures.add(inp)
v = f.bodies.item(0).physicalProperties.volume
assert abs(v - 9 * math.pi) < 1e-3, v
result = {'volume_cm3': v}
''')

test('sweep along a path')(r'''
sk1 = root.sketches.add(root.xYConstructionPlane)
line = sk1.sketchCurves.sketchLines.addByTwoPoints(P3(0, 0, 0), P3(0, 5, 0))
sk2 = root.sketches.add(root.xZConstructionPlane)
sk2.sketchCurves.sketchCircles.addByCenterRadius(P3(0, 0, 0), 0.5)
path = root.features.createPath(line)
inp = root.features.sweepFeatures.createInput(sk2.profiles.item(0), path, FO.NewBodyFeatureOperation)
f = root.features.sweepFeatures.add(inp)
v = f.bodies.item(0).physicalProperties.volume
assert abs(v - math.pi * 0.25 * 5) < 1e-3, v
result = {'volume_cm3': v}
''')

test('loft between two profiles')(r'''
sk1 = root.sketches.add(root.xYConstructionPlane)
sk1.sketchCurves.sketchCircles.addByCenterRadius(P3(0, 0, 0), 1.0)
pi = root.constructionPlanes.createInput()
pi.setByOffset(root.xYConstructionPlane, VI.createByReal(3.0))
pl = root.constructionPlanes.add(pi)
sk2 = root.sketches.add(pl)
sk2.sketchCurves.sketchCircles.addByCenterRadius(P3(0, 0, 0), 0.5)
li = root.features.loftFeatures.createInput(FO.NewBodyFeatureOperation)
li.loftSections.add(sk1.profiles.item(0))
li.loftSections.add(sk2.profiles.item(0))
f = root.features.loftFeatures.add(li)
v = f.bodies.item(0).physicalProperties.volume
assert abs(v - math.pi * 1.75) < 0.05, v
result = {'volume_cm3': v}
''')

test('fillet + shell')(r'''
f = box(root, 10, 10, 10)
b = f.bodies.item(0)
v0 = b.physicalProperties.volume
fi = root.features.filletFeatures.createInput()
fi.addConstantRadiusEdgeSet(coll(*list(b.edges)), VI.createByReal(1.0), True)
root.features.filletFeatures.add(fi)
b = root.bRepBodies.item(0)
v1 = b.physicalProperties.volume
assert v1 < v0, (v0, v1)
top = max(b.faces, key=lambda fc: fc.centroid.z)
si = root.features.shellFeatures.createInput(coll(top), False)
si.insideThickness = VI.createByReal(0.5)
root.features.shellFeatures.add(si)
v2 = root.bRepBodies.item(0).physicalProperties.volume
assert v2 < v1, (v1, v2)
result = {'v_box': v0, 'v_filleted': v1, 'v_shelled': v2}
''')

test('chamfer')(r'''
f = box(root, 10, 10, 10)
b = f.bodies.item(0)
v0 = b.physicalProperties.volume
ci = root.features.chamferFeatures.createInput2()
ci.chamferEdgeSets.addEqualDistanceChamferEdgeSet(coll(*list(b.edges)), VI.createByReal(0.5), True)
root.features.chamferFeatures.add(ci)
v1 = root.bRepBodies.item(0).physicalProperties.volume
assert v1 < v0, (v0, v1)
result = {'v_box': v0, 'v_chamfered': v1}
''')

test('hole feature')(r'''
f = box(root, 10, 10, 4)
b = f.bodies.item(0)
v0 = b.physicalProperties.volume
top = max(b.faces, key=lambda fc: fc.centroid.z)
sk = root.sketches.add(top)
pt = sk.sketchPoints.add(sk.modelToSketchSpace(top.centroid))
hi = root.features.holeFeatures.createSimpleInput(VI.createByReal(1.0))
hi.setPositionBySketchPoint(pt)
hi.setDistanceExtent(VI.createByReal(2.0))
root.features.holeFeatures.add(hi)
removed = v0 - root.bRepBodies.item(0).physicalProperties.volume
assert 1.4 < removed < 1.9, removed
result = {'removed_cm3': removed}
''')

test('rectangular pattern + mirror + circular pattern')(r'''
f = box(root, 2, 2, 2)
b = f.bodies.item(0)
ri = root.features.rectangularPatternFeatures.createInput(
    coll(b), root.xConstructionAxis, VI.createByReal(3), VI.createByReal(5),
    adsk.fusion.PatternDistanceType.SpacingPatternDistanceType)
ri.quantityTwo = VI.createByReal(1)
root.features.rectangularPatternFeatures.add(ri)
n1 = root.bRepBodies.count
assert n1 == 3, n1
mi = root.features.mirrorFeatures.createInput(coll(b), root.yZConstructionPlane)
root.features.mirrorFeatures.add(mi)
n2 = root.bRepBodies.count
assert n2 == 4, n2
ci = root.features.circularPatternFeatures.createInput(coll(b), root.zConstructionAxis)
ci.quantity = VI.createByReal(4)
ci.totalAngle = VI.createByString('360 deg')
root.features.circularPatternFeatures.add(ci)
n3 = root.bRepBodies.count
assert n3 >= 7, n3
result = {'after_rect': n1, 'after_mirror': n2, 'after_circular': n3}
''')

test('boolean combine (join)')(r'''
f1 = box(root, 4, 4, 4)
b1 = f1.bodies.item(0)
f2 = box(root, 4, 4, 4, x0=2, y0=2)
b2 = f2.bodies.item(0)
ci = root.features.combineFeatures.createInput(b1, coll(b2))
ci.operation = FO.JoinFeatureOperation
root.features.combineFeatures.add(ci)
assert root.bRepBodies.count == 1, root.bRepBodies.count
v = root.bRepBodies.item(0).physicalProperties.volume
assert abs(v - 112) < 1e-3, v
result = {'volume_cm3': v}
''')

test('components + rigid joint (assembly)')(r'''
o1 = root.occurrences.addNewComponent(adsk.core.Matrix3D.create())
o1.component.name = 'Base'
box(o1.component, 4, 4, 1)
o2 = root.occurrences.addNewComponent(adsk.core.Matrix3D.create())
o2.component.name = 'Post'
box(o2.component, 1, 1, 3, x0=10, y0=10)
b1 = o1.bRepBodies.item(0)
b2 = o2.bRepBodies.item(0)
top1 = max(b1.faces, key=lambda fc: fc.centroid.z)
bot2 = min(b2.faces, key=lambda fc: fc.centroid.z)
g1 = adsk.fusion.JointGeometry.createByPlanarFace(top1, None, adsk.fusion.JointKeyPointTypes.CenterKeyPoint)
g2 = adsk.fusion.JointGeometry.createByPlanarFace(bot2, None, adsk.fusion.JointKeyPointTypes.CenterKeyPoint)
ji = root.joints.createInput(g2, g1)
ji.setAsRigidJointMotion()
ji.isFlipped = True
j = root.joints.add(ji)
assert j is not None
z = o2.bRepBodies.item(0).boundingBox.minPoint.z
assert abs(z - 1.0) < 1e-3, z
result = {'occurrences': root.occurrences.count, 'joints': root.joints.count, 'post_bottom_z': z}
''')

test('user parameters drive geometry (parametric edit)')(r'''
design.userParameters.add('w', VI.createByString('10 cm'), 'cm', 'width')
sk = root.sketches.add(root.xYConstructionPlane)
sk.sketchCurves.sketchLines.addTwoPointRectangle(P3(0, 0, 0), P3(5, 5, 0))
inp = root.features.extrudeFeatures.createInput(sk.profiles.item(0), FO.NewBodyFeatureOperation)
inp.setDistanceExtent(False, VI.createByString('w'))
root.features.extrudeFeatures.add(inp)
v1 = root.bRepBodies.item(0).physicalProperties.volume
design.userParameters.itemByName('w').expression = '20 cm'
v2 = root.bRepBodies.item(0).physicalProperties.volume
assert abs(v1 - 250) < 1e-3 and abs(v2 - 500) < 1e-3, (v1, v2)
result = {'v_w10': v1, 'v_w20': v2}
''')

test('timeline rollback + edit feature')(r'''
box(root, 2, 2, 2)
assert design.timeline.count >= 2, design.timeline.count
design.timeline.markerPosition = 0
assert root.bRepBodies.count == 0
design.timeline.moveToEnd()
assert root.bRepBodies.count == 1
ext = root.features.extrudeFeatures.item(0)
ext.extentOne.distance.expression = '4 cm'
v = root.bRepBodies.item(0).physicalProperties.volume
assert abs(v - 16) < 1e-3, v
result = {'timeline_items': design.timeline.count, 'volume_after_edit': v}
''')

test('appearance + material assignment (wood)')(r'''
f = box(root, 2, 2, 2)
b = f.bodies.item(0)
found_ap = found_mat = None
for lib in app.materialLibraries:
    if found_ap is None:
        for ap in lib.appearances:
            if 'oak' in ap.name.lower():
                found_ap = ap
                break
    if found_mat is None:
        for m in lib.materials:
            if 'oak' in m.name.lower():
                found_mat = m
                break
    if found_ap and found_mat:
        break
assert found_ap, 'no oak appearance in libraries'
b.appearance = design.appearances.addByCopy(found_ap, 'oak_test')
res = {'appearance': found_ap.name}
if found_mat:
    b.material = design.materials.addByCopy(found_mat, 'oak_mat_test')
    res['material'] = found_mat.name
result = res
''')

test('measure: bounding box, mass properties, distance')(r'''
f = box(root, 2, 3, 4)
b = f.bodies.item(0)
bb = b.boundingBox
dims = (bb.maxPoint.x - bb.minPoint.x, bb.maxPoint.y - bb.minPoint.y, bb.maxPoint.z - bb.minPoint.z)
assert all(abs(a - e) < 1e-6 for a, e in zip(dims, (2, 3, 4))), dims
pp = b.physicalProperties
res = app.measureManager.measureMinimumDistance(b.faces.item(0), b.faces.item(1))
result = {'dims_cm': dims, 'volume': pp.volume, 'area': pp.area, 'com': [pp.centerOfMass.x, pp.centerOfMass.y, pp.centerOfMass.z],
          'min_distance': res.value}
''')

test('sketch variety: spline, arc, text')(r'''
sk = root.sketches.add(root.xYConstructionPlane)
pts = coll(P3(0, 0, 0), P3(1, 1, 0), P3(2, 0, 0), P3(3, 1, 0))
sk.sketchCurves.sketchFittedSplines.add(pts)
sk.sketchCurves.sketchArcs.addByThreePoints(P3(0, 3, 0), P3(1, 4, 0), P3(2, 3, 0))
ti = sk.sketchTexts.createInput2('OAK', 0.5)
ti.setAsMultiLine(P3(0, 6, 0), P3(4, 7, 0), adsk.core.HorizontalAlignments.LeftHorizontalAlignment,
                  adsk.core.VerticalAlignments.TopVerticalAlignment, 0)
sk.sketchTexts.add(ti)
result = {'splines': sk.sketchCurves.sketchFittedSplines.count, 'arcs': sk.sketchCurves.sketchArcs.count,
          'texts': sk.sketchTexts.count}
''')

test('export: STEP STL F3D OBJ 3MF IGES SAT + sketch DXF')(r'''
f = box(root, 3, 3, 3)
b = f.bodies.item(0)
d = tempfile.mkdtemp(prefix='fbtest_')
em = design.exportManager
out = {}
def run(name, make):
    try:
        opts = make()
        em.execute(opts)
        out[name] = os.path.getsize(opts.filename)
    except Exception as e:
        out[name] = 'ERR: ' + str(e)[:120]
run('step', lambda: em.createSTEPExportOptions(os.path.join(d, 'a.step')))
run('stl', lambda: em.createSTLExportOptions(b, os.path.join(d, 'a.stl')))
run('f3d', lambda: em.createFusionArchiveExportOptions(os.path.join(d, 'a.f3d')))
run('obj', lambda: em.createOBJExportOptions(b, os.path.join(d, 'a.obj')))
run('3mf', lambda: em.createC3MFExportOptions(b, os.path.join(d, 'a.3mf')))
run('iges', lambda: em.createIGESExportOptions(os.path.join(d, 'a.igs')))
run('sat', lambda: em.createSATExportOptions(os.path.join(d, 'a.sat')))
try:
    sk = root.sketches.item(0)
    ok = sk.saveAsDXF(os.path.join(d, 'a.dxf'))
    out['dxf'] = os.path.getsize(os.path.join(d, 'a.dxf')) if ok else 'ERR: saveAsDXF false'
except Exception as e:
    out['dxf'] = 'ERR: ' + str(e)[:120]
shutil.rmtree(d, ignore_errors=True)
bad = {k: v for k, v in out.items() if isinstance(v, str)}
result = {'sizes_bytes': out, 'failed': bad}
assert not bad, bad
''')

test('export STEP then import it back')(r'''
box(root, 3, 3, 3)
d = tempfile.mkdtemp(prefix='fbtest_')
p = os.path.join(d, 'rt.step')
design.exportManager.execute(design.exportManager.createSTEPExportOptions(p))
im = app.importManager
ok = im.importToTarget(im.createSTEPImportOptions(p), root)
shutil.rmtree(d, ignore_errors=True)
assert ok
assert root.occurrences.count >= 1, root.occurrences.count
result = {'imported_occurrences': root.occurrences.count}
''')

test('camera + viewport capture to PNG')(r'''
box(root, 3, 3, 3)
vp = app.activeViewport
cam = vp.camera
cam.viewOrientation = adsk.core.ViewOrientations.IsoTopRightViewOrientation
vp.camera = cam
vp.fit()
p = os.path.join(tempfile.gettempdir(), 'fb_viewport.png')
ok = vp.saveAsImageFile(p, 800, 600)
assert ok and os.path.getsize(p) > 1000, ok
result = {'path': p, 'bytes': os.path.getsize(p)}
''')

test('selection API')(r'''
f = box(root, 2, 2, 2)
b = f.bodies.item(0)
ui.activeSelections.clear()
ui.activeSelections.add(b)
n = ui.activeSelections.count
ui.activeSelections.clear()
assert n == 1, n
result = {'selected': n}
''')

test('API surface: CAM / drawing / render / sheet metal / mesh present')(r'''
import adsk.cam
res = {'adsk.cam': True}
try:
    import adsk.drawing
    res['adsk.drawing'] = True
except Exception as e:
    res['adsk.drawing'] = 'missing: ' + str(e)[:80]
try:
    res['cam_product'] = doc.products.itemByProductType('CAMProductType') is not None
except Exception as e:
    res['cam_product'] = 'not created until CAM workspace is opened'
try:
    res['render_manager'] = design.renderManager is not None
except Exception as e:
    res['render_manager'] = 'ERR: ' + str(e)[:80]
res['feature_collections'] = sorted(n for n in dir(root.features) if n.endswith('Features'))
result = res
''')


test('render: real local render to PNG')(r"""
box(root, 5, 4, 3)
app.activeViewport.goHome()
r = design.renderManager.rendering
r.renderQuality = 25; r.resolutionWidth = 480; r.resolutionHeight = 360
out = os.path.join(tempfile.gettempdir(), 'fb_render_test.png')
if os.path.exists(out): os.remove(out)
fut = r.startLocalRender(out)
import time
t0 = time.time()
while time.time() - t0 < 90:
    adsk.doEvents()
    if fut.progress >= 1.0 and os.path.exists(out) and os.path.getsize(out) > 1000:
        break
    time.sleep(0.5)
assert os.path.exists(out) and os.path.getsize(out) > 1000, 'no render file'
result = {'bytes': os.path.getsize(out), 'secs': round(time.time() - t0, 1)}
""")

test('configurations: create configured design')(r"""
box(root, 2, 2, 2)
design.createConfiguredDesign()
assert design.isConfiguredDesign
result = {'rows': design.configurationTopTable.rows.count}
""")

test('CAM: open workspace, create product + setup input')(r"""
import adsk.cam
box(root, 4, 3, 1)
ui.workspaces.itemById('CAMEnvironment').activate()
adsk.doEvents()
try:
    cam = adsk.cam.CAM.cast(doc.products.itemByProductType('CAMProductType'))
    assert cam, 'CAM product missing'
    si = cam.setups.createInput(adsk.cam.OperationTypes.MillingOperation)
    result = {'cam': True, 'setups': cam.setups.count, 'setupInput': si is not None}
finally:
    ui.workspaces.itemById('FusionSolidEnvironment').activate()
""")

test('UI command by ID (anything a human can click)')(r"""
cd = ui.commandDefinitions
need = ['Extrude', 'SketchCreate', 'SaveDocumentCommand', 'NewDrawingMenuCommand', 'InCanvasRenderCommand', 'FitCommand']
found = {i: bool(cd.itemById(i)) for i in need}
assert all(found.values()), found
result = {'total_commands': cd.count, 'found': found}
""")

test('sheet metal: API entry points')(r"""
fl = root.features.flangeFeatures
assert hasattr(fl, 'createBaseFlangeInput') and hasattr(fl, 'createContourFlangeInput') and hasattr(fl, 'createEdgeFlangeInput')
result = {'flange': True, 'unfold': hasattr(root.features, 'unfoldFeatures'), 'rules_api': hasattr(design, 'designSheetMetalRules')}
""")

test('mesh + T-spline: API entry points')(r"""
f = root.features
names = [n for n in dir(f) if n.startswith('mesh')]
assert len(names) >= 10, names
result = {'mesh_feature_collections': len(names), 'add_mesh_by_data': hasattr(root.meshBodies, 'addByTriangleMeshData')}
""")

test('animation + snapshots: API entry points')(r"""
# Instances raise 'assetRoot' InternalValidationError until the Animation workspace is opened, so check the class API.
result = {'storyboards': hasattr(adsk.fusion.AnimationManager, 'storyboards'), 'snapshots': hasattr(adsk.fusion.Snapshots, 'add'), 'note': 'instance needs Animation workspace active'}
assert result['storyboards'] and result['snapshots']
""")


def build(body):
    return (PRE + 'try:\n' + textwrap.indent(body.strip('\n'), '    ') +
            '\nfinally:\n    try:\n        doc.close(False)\n    except Exception:\n        pass\n')


def main():
    words = [w.lower() for w in sys.argv[1:]]
    chosen = [(n, b) for n, b in TESTS if not words or any(w in n.lower() for w in words)]
    report, passed = [], 0
    for name, body in chosen:
        t0 = time.time()
        r = call(build(body))
        dt = time.time() - t0
        ok = bool(r.get('ok'))
        passed += ok
        line = 'PASS' if ok else 'FAIL'
        detail = json.dumps(r.get('result'), default=str)[:300] if ok else (r.get('error') or '').strip().splitlines()[-1][:300]
        print('%s  %-58s %5.1fs  %s' % (line, name, dt, detail), flush=True)
        report.append({'name': name, 'ok': ok, 'seconds': round(dt, 2), 'result': r.get('result'), 'error': r.get('error')})
    print('\n%d/%d passed' % (passed, len(chosen)))
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'last_report.json'), 'w') as f:
        json.dump(report, f, indent=2, default=str)
    return 0 if passed == len(chosen) else 1


if __name__ == '__main__':
    sys.exit(main())
