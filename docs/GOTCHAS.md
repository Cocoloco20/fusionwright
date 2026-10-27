# Fusion API gotchas (found by live testing on Fusion 2706.x)

Each of these cost a failed test before it was understood. They are baked into the scripts in `src/fusionwright/backends/fusion_scripts.py`.

| Symptom | Cause | Fix |
|---|---|---|
| A rectangular pattern makes 9 bodies instead of 3 | `quantityTwo` defaults to 3 | set `quantityTwo = ValueInput.createByReal(1)` for a 1-D pattern |
| Joined parts sit on the wrong side of each other | rigid joint between mating faces needs the flip | `jointInput.isFlipped = True` |
| Cutting the wrong region from a face sketch | a sketch on a face also yields an outer-face profile | choose the profile by area (the circle is the smallest) |
| `ExtrudeFeatureInput` cut from a top face does nothing | wrong extent direction | `setOneSideExtent(DistanceExtentDefinition, ExtentDirections.NegativeExtentDirection)` |
| Box above Z=0 | extrude starts on the sketch plane | `input.startExtent = OffsetStartDefinition.create(ValueInput.createByReal(z_cm))` |
| `itemByProductType('CAMProductType')` raises | CAM product is created lazily | `ui.workspaces.itemById('CAMEnvironment').activate()` first, then switch back |
| 3MF export fails | wrong method name | `exportManager.createC3MFExportOptions(entity, path)` |
| `renderQuality` raises | valid range is 25-100 | clamp the value |
| `fusion_look` returned the same image for every view | `ViewOrientations` presets did not reliably change the captured frame | set `camera.eye/target/upVector` from the bounding box, `adsk.doEvents()`, then `viewport.fit()` |
| `designSheetMetalRules.count` raises `smDataRoot` | sheet-metal data does not exist until the design is a sheet-metal design | only touch sheet-metal rules inside a sheet-metal component |
| `design.animationManager`/`snapshots` raise `assetRoot` | the animation workspace has not been opened | check class API, or activate the Animation workspace |
| `DrawingManager.createDrawingInput()` rejects a design | it needs a saved `DataFile`, not a live document | drawings require a cloud-saved design |
| Each tool call must finish fast | add-ins run code on the main thread | chunk big builds (this project builds 20 boards per call) |
