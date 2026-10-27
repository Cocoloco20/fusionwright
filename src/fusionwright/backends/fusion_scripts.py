"""Python source that runs INSIDE Fusion (through the bridge add-in). Each script receives ARGS (a dict)
and must assign a JSON-serialisable value to `result`. All lengths in/out are inches; Fusion's internal
unit is centimetres, converted by IN = 2.54.

Gotchas baked in (all found by live testing against Fusion 2706.x):
  * a rectangular pattern's quantityTwo defaults to 3, not 1
  * rigid joints between mating faces need isFlipped = True
  * a sketch drawn on a face yields an extra outer-face profile - pick profiles by area
  * extrude-cut from a top face needs a NegativeExtentDirection one-sided extent
  * the CAM product only exists after the CAM workspace has been opened
"""
from __future__ import annotations

import json

HELPERS = r'''
import os, math, tempfile, json
P3 = adsk.core.Point3D.create
VI = adsk.core.ValueInput
FO = adsk.fusion.FeatureOperations
IN = 2.54          # cm per inch
CM3_PER_IN3 = 16.387064

def _find_design():
    d = adsk.fusion.Design.cast(app.activeProduct)
    if d is None and app.activeDocument is not None:
        d = adsk.fusion.Design.cast(app.activeDocument.products.itemByProductType('DesignProductType'))
    if d is None:
        raise RuntimeError('No active Fusion design. Open or create a Design document in Fusion first.')
    return d

design = _find_design()
root = design.rootComponent

def coll(*items):
    c = adsk.core.ObjectCollection.create()
    for i in items:
        c.add(i)
    return c

def board(name, x, y, z, sx, sy, sz):
    """New component holding one box. Position/size in inches. Returns (occurrence, body)."""
    occ = root.occurrences.addNewComponent(adsk.core.Matrix3D.create())
    comp = occ.component
    comp.name = name
    sk = comp.sketches.add(comp.xYConstructionPlane)
    sk.sketchCurves.sketchLines.addTwoPointRectangle(P3(x * IN, y * IN, 0), P3((x + sx) * IN, (y + sy) * IN, 0))
    inp = comp.features.extrudeFeatures.createInput(sk.profiles.item(0), FO.NewBodyFeatureOperation)
    if abs(z) > 1e-9:
        inp.startExtent = adsk.fusion.OffsetStartDefinition.create(VI.createByReal(z * IN))
    inp.setDistanceExtent(False, VI.createByReal(sz * IN))
    feat = comp.features.extrudeFeatures.add(inp)
    body = feat.bodies.item(0)
    body.name = name
    return occ, body

def find_appearance(terms):
    # terms are in priority order; first term with any match wins
    for t in terms:
        for lib in app.materialLibraries:
            for ap in lib.appearances:
                if t in ap.name.lower():
                    return ap
    return None

def bodies_all():
    seen, out = set(), []
    for b in root.bRepBodies:
        out.append(b)
    for occ in root.allOccurrences:
        for b in occ.bRepBodies:
            out.append(b)
    return out
'''

INSPECT = r'''
detail = ARGS.get('detail', 'summary')
bs = bodies_all()
rows, lo, hi = [], [1e9] * 3, [-1e9] * 3
vol = 0.0
for b in bs:
    bb = b.boundingBox
    mn, mx = [bb.minPoint.x, bb.minPoint.y, bb.minPoint.z], [bb.maxPoint.x, bb.maxPoint.y, bb.maxPoint.z]
    for i in range(3):
        lo[i], hi[i] = min(lo[i], mn[i]), max(hi[i], mx[i])
    v = b.volume / CM3_PER_IN3
    vol += v
    rows.append({'name': b.name, 'min_in': [round(c / IN, 3) for c in mn], 'size_in': [round((mx[i] - mn[i]) / IN, 3) for i in range(3)],
                 'volume_in3': round(v, 3), 'valid': b.isValid, 'appearance': b.appearance.name if b.appearance else None})
tl = design.timeline
bad = []
for i in range(tl.count):
    it = tl.item(i)
    try:
        if it.healthState != adsk.fusion.FeatureHealthStates.HealthyFeatureHealthState:
            bad.append({'index': i, 'name': it.name, 'state': str(it.healthState), 'message': it.errorOrWarningMessage})
    except Exception:
        pass
res = {'document': app.activeDocument.name if app.activeDocument else None,
       'units': design.unitsManager.defaultLengthUnits, 'design_type': str(design.designType),
       'components': root.allOccurrences.count, 'bodies': len(bs),
       'overall_size_in': [round((hi[i] - lo[i]) / IN, 3) for i in range(3)] if bs else None,
       'total_volume_in3': round(vol, 2), 'timeline_items': tl.count, 'timeline_problems': bad[:20],
       'invalid_bodies': [r['name'] for r in rows if not r['valid']][:20]}
if detail == 'full':
    res['bodies_detail'] = rows[:300]
    res['parameters'] = [{'name': p.name, 'expression': p.expression} for p in design.userParameters]
result = res
'''

INTERFERENCE = r'''
bs = bodies_all()
if len(bs) < 2:
    result = {'checked': len(bs), 'interferences': []}
else:
    inp = design.createInterferenceInput(coll(*bs))
    inp.areCoincidentFacesInterfering = False
    res = design.analyzeInterference(inp)
    out = []
    for i in range(min(res.count, 50)):
        r = res.item(i)
        out.append({'a': r.entityOne.name, 'b': r.entityTwo.name,
                    'volume_in3': round(r.interferenceBody.volume / CM3_PER_IN3, 4) if r.interferenceBody else None})
    result = {'checked': len(bs), 'count': res.count, 'interferences': out}
'''

LOOK = r'''
# NOTE: the ViewOrientations presets did not reliably change the captured frame (every view came back
# identical to the iso one), so the camera is placed explicitly from the model's bounding box instead.
DIRS = {'iso': ((1, -1, 0.8), (0, 0, 1)), 'front': ((0, -1, 0), (0, 0, 1)), 'back': ((0, 1, 0), (0, 0, 1)),
        'left': ((-1, 0, 0), (0, 0, 1)), 'right': ((1, 0, 0), (0, 0, 1)), 'top': ((0, 0, 1), (0, 1, 0)),
        'bottom': ((0, 0, -1), (0, -1, 0))}
vp = app.activeViewport
w, h = int(ARGS.get('width', 900)), int(ARGS.get('height', 700))
bb = root.boundingBox
c = adsk.core.Point3D.create((bb.minPoint.x + bb.maxPoint.x) / 2, (bb.minPoint.y + bb.maxPoint.y) / 2,
                             (bb.minPoint.z + bb.maxPoint.z) / 2)
diag = max(bb.maxPoint.distanceTo(bb.minPoint), 10.0)
d = tempfile.mkdtemp(prefix='fw_look_')
paths = {}
for v in ARGS.get('views', ['iso']):
    dirv, up = DIRS[v]
    n = math.sqrt(sum(x * x for x in dirv))
    cam = vp.camera
    cam.cameraType = adsk.core.CameraTypes.OrthographicCameraType if ARGS.get('orthographic', v != 'iso') else adsk.core.CameraTypes.PerspectiveCameraType
    cam.target = c
    cam.eye = adsk.core.Point3D.create(c.x + 3 * diag * dirv[0] / n, c.y + 3 * diag * dirv[1] / n, c.z + 3 * diag * dirv[2] / n)
    cam.upVector = adsk.core.Vector3D.create(*up)
    cam.isSmoothTransition = False
    vp.camera = cam
    adsk.doEvents()
    vp.fit()
    adsk.doEvents()
    p = os.path.join(d, v + '.png')
    if not vp.saveAsImageFile(p, w, h):
        raise RuntimeError('saveAsImageFile failed for view ' + v)
    paths[v] = p
result = {'paths': paths}
'''

EXPORT = r'''
fmt, path = ARGS['format'].lower(), ARGS['path']
os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
em = design.exportManager
makers = {
    'step': lambda: em.createSTEPExportOptions(path),
    'stl': lambda: em.createSTLExportOptions(root, path),
    'f3d': lambda: em.createFusionArchiveExportOptions(path),
    'obj': lambda: em.createOBJExportOptions(root, path),
    '3mf': lambda: em.createC3MFExportOptions(root, path),
    'iges': lambda: em.createIGESExportOptions(path),
    'sat': lambda: em.createSATExportOptions(path),
}
if fmt not in makers:
    raise RuntimeError('Unsupported format %r. Use one of: %s' % (fmt, ', '.join(sorted(makers))))
em.execute(makers[fmt]())
result = {'path': path, 'bytes': os.path.getsize(path)}
'''

RENDER = r'''
import time
r = design.renderManager.rendering
r.renderQuality = max(25, min(100, int(ARGS.get('quality', 25))))
r.resolutionWidth, r.resolutionHeight = int(ARGS.get('width', 960)), int(ARGS.get('height', 720))
out = ARGS['path']
if os.path.exists(out):
    os.remove(out)
fut = r.startLocalRender(out)
t0 = time.time()
limit = float(ARGS.get('timeout', 70))
while time.time() - t0 < limit:
    adsk.doEvents()
    if fut.progress >= 1.0 and os.path.exists(out) and os.path.getsize(out) > 1000:
        break
    time.sleep(0.4)
ok = os.path.exists(out) and os.path.getsize(out) > 1000
result = {'ok': ok, 'path': out, 'progress': fut.progress, 'seconds': round(time.time() - t0, 1)}
'''

API = r'''
import adsk.cam, adsk.drawing
q = ARGS['query'].strip()
mods = {'core': adsk.core, 'fusion': adsk.fusion, 'cam': adsk.cam, 'drawing': adsk.drawing}
def doc1(o, n=140):
    d = (getattr(o, '__doc__', None) or '').strip().replace('\n', ' ')
    return d[:n]
cls = None
for mn, m in mods.items():
    if hasattr(m, q) and isinstance(getattr(m, q), type):
        cls, cname = getattr(m, q), 'adsk.%s.%s' % (mn, q)
        break
if cls is None and '.' in q:
    qc = q.split('.')[-1]
    for mn, m in mods.items():
        if hasattr(m, qc) and isinstance(getattr(m, qc), type):
            cls, cname = getattr(m, qc), 'adsk.%s.%s' % (mn, qc)
            break
if cls is not None:
    members = []
    for n in sorted(dir(cls)):
        if n.startswith('_') or n in ('cast', 'classType', 'thisown', 'this', 'objectType', 'isValid'):
            continue
        members.append({'name': n, 'doc': doc1(getattr(cls, n), 150)})
    result = {'class': cname, 'doc': doc1(cls, 500), 'members': members[:ARGS.get('limit', 60)]}
else:
    ql = q.lower().split()
    hits = []
    for mn, m in mods.items():
        for n in dir(m):
            o = getattr(m, n)
            if isinstance(o, type) and all(t in n.lower() for t in ql) and not n.endswith('_classType'):
                hits.append('adsk.%s.%s' % (mn, n))
    mem = []
    if not hits:
        for mn, m in mods.items():
            for n in dir(m):
                o = getattr(m, n)
                if isinstance(o, type):
                    for a in dir(o):
                        if not a.startswith('_') and all(t in a.lower() for t in ql):
                            mem.append('adsk.%s.%s.%s' % (mn, n, a))
    result = {'matching_classes': hits[:40], 'matching_members': mem[:40],
              'hint': 'Pass an exact class name (e.g. ExtrudeFeatureInput) to list its members.'}
'''

ROLLBACK = r'''
tl = design.timeline
target = int(ARGS['count'])
removed = 0
for i in range(tl.count - 1, target - 1, -1):
    try:
        tl.item(i).entity.deleteMe()
        removed += 1
    except Exception:
        pass
result = {'timeline_items': tl.count, 'target': target, 'removed': removed}
'''

COUNT = r'''
result = {'timeline_items': design.timeline.count}
'''

UI_COMMAND = r'''
cd = ui.commandDefinitions
if ARGS.get('search'):
    s = ARGS['search'].lower()
    hits = []
    for i in range(cd.count):
        c = cd.item(i)
        if s in (c.id or '').lower() or s in (c.name or '').lower():
            hits.append({'id': c.id, 'name': c.name})
            if len(hits) >= 40:
                break
    result = {'matches': hits}
else:
    c = cd.itemById(ARGS['id'])
    if c is None:
        raise RuntimeError('Unknown command id %r. Search with ui_command(search=...) first.' % ARGS['id'])
    c.execute()
    result = {'executed': ARGS['id'], 'note': 'If a dialog opened, finish or cancel it in Fusion.'}
'''


def render(script: str, **args) -> str:
    """Assemble a full program: ARGS + helpers + script."""
    return f"import json\nARGS = json.loads({json.dumps(json.dumps(args))})\n" + HELPERS + "\n" + script
