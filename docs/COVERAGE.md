# Coverage: what an AI can and cannot do in Fusion through this project

"Everything a human can do" is not achievable through any public API. This matrix is the honest picture, backed by tests where marked.

| Area | Status | Notes |
|---|---|---|
| Sketching (lines, arcs, circles, splines, text), constraints, dimensions | Tested | `capability_suite.py` |
| Solid features: extrude, cut, revolve, sweep, loft, fillet, chamfer, shell, hole | Tested | |
| Patterns, mirror, combine (boolean) | Tested | note the `quantityTwo` default |
| Components, joints (rigid), assembly | Tested | joint flip gotcha |
| User parameters and parametric edits, timeline rollback/edit | Tested | |
| Materials and appearances | Tested | oak and a light-wood (pine) appearance applied per material |
| Measurement (bbox, mass properties, distance), interference | Tested | |
| Export STEP/STL/F3D/OBJ/3MF/IGES/SAT, sketch DXF; STEP import | Tested | local only |
| Viewport screenshots from named views | Tested | explicit camera placement |
| Photoreal render | Tested | local renderer, quality 25-100 |
| CAM: create product, setup input | Partially tested | toolpath generation is not exercised |
| Configurations | Partially tested | designs can be made configured; rules API untested |
| Sheet metal, mesh, T-spline, generative, simulation, animation | API present, not exercised | entry points verified only |
| Drawings (Fusion-native) | Not automated | requires a design saved to the Autodesk cloud; this project ships its own SVG drawings instead |
| Any menu command | Available | `fusion_ui_command` runs any of ~3,000 command ids; dialogs still need finishing in Fusion |
| Cloud data (Fusion Team/hubs) | Out of scope | by design nothing is saved to the cloud; Autodesk's Fusion Data MCP covers this |
| Drag gestures, canvas-only manipulations | Manual | would need computer-use style control |
