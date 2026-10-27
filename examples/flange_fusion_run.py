"""Fusion route: a flanged bushing built with the real Fusion API (sketch -> extrude -> holes -> fillet).

Paste this as the `code` of `fusion_run`. Predefined there: app, ui, design, root, adsk, P3, VI, FO, coll, IN.
Fusion works in centimetres internally, so every length below is in cm. Assign your answer to `result`.
Tip: call `fusion_api('ExtrudeFeatures')` first when you adapt this to something else.
"""
import math

OD, ID, FLANGE_D, FLANGE_T, LENGTH = 3.0, 1.6, 6.0, 0.6, 5.0          # cm
BOLT_CIRCLE, BOLT_D, BOLTS = 4.5, 0.5, 4

comp = root
xy = comp.xYConstructionPlane

# 1) flange disc + bushing tube as one profile stack
sk = comp.sketches.add(xy)
sk.name = "flange profile"
sk.sketchCurves.sketchCircles.addByCenterRadius(P3(0, 0, 0), FLANGE_D / 2)
sk.sketchCurves.sketchCircles.addByCenterRadius(P3(0, 0, 0), ID / 2)
ext = comp.features.extrudeFeatures
ring = max(sk.profiles, key=lambda p: p.areaProperties().area)             # disc minus bore, not the bore itself
flange = ext.addSimple(ring, VI.createByReal(FLANGE_T),
                       FO.NewBodyFeatureOperation)
flange.name = "flange"

sk2 = comp.sketches.add(xy)
sk2.name = "tube profile"
sk2.sketchCurves.sketchCircles.addByCenterRadius(P3(0, 0, 0), OD / 2)
sk2.sketchCurves.sketchCircles.addByCenterRadius(P3(0, 0, 0), ID / 2)
tube_prof = max(sk2.profiles, key=lambda p: p.areaProperties().area)         # the ring between OD and ID
inp = ext.createInput(tube_prof, FO.JoinFeatureOperation)
inp.setDistanceExtent(False, VI.createByReal(LENGTH))
tube = ext.add(inp)
tube.name = "tube"

# 2) bolt holes on the flange
sk3 = comp.sketches.add(xy)
sk3.name = "bolt holes"
for i in range(BOLTS):
    a = 2 * math.pi * i / BOLTS
    sk3.sketchCurves.sketchCircles.addByCenterRadius(
        P3(BOLT_CIRCLE / 2 * math.cos(a), BOLT_CIRCLE / 2 * math.sin(a), 0), BOLT_D / 2)
for prof in sk3.profiles:
    cut = ext.createInput(prof, FO.CutFeatureOperation)
    cut.setDistanceExtent(False, VI.createByReal(FLANGE_T))
    ext.add(cut)

body = comp.bRepBodies.item(0)
body.name = "flanged bushing"
# check the model against the arithmetic, not just "it ran"
expected = (math.pi * ((FLANGE_D / 2) ** 2 - (ID / 2) ** 2) * FLANGE_T                      # flange ring
            + math.pi * ((OD / 2) ** 2 - (ID / 2) ** 2) * (LENGTH - FLANGE_T)               # tube above it
            - BOLTS * math.pi * (BOLT_D / 2) ** 2 * FLANGE_T)                               # bolt holes
result = {"bodies": comp.bRepBodies.count, "valid": body.isValid,
          "volume_cm3": round(body.volume, 3), "expected_cm3": round(expected, 3)}
