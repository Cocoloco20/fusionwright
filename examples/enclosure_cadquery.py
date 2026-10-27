"""Open-source route (no Fusion, no account): a two-part electronics enclosure with screw posts and a vent slot.

Paste this as the `code` of the `cad_run` tool, or ask your AI: "make a 80 x 50 x 25 mm enclosure for a PCB".
Predefined inside cad_run: `cq`, `OUT`. Assign `result` (here a dict, so each part gets its own colour).
Units: millimetres.
"""
L, W, H, T = 80.0, 50.0, 25.0, 2.0          # outer length / width / height, wall thickness

base = (cq.Workplane("XY").box(L, W, H, centered=(True, True, False))
        .faces(">Z").shell(-T)                                   # hollow, open top
        .edges("|Z").fillet(3.0))

# four screw posts in the corners, with pilot holes
posts = (cq.Workplane("XY").workplane(offset=T)
         .rect(L - 12, W - 12, forConstruction=True).vertices()
         .circle(3.5).extrude(H - T - 2.0)
         .faces(">Z").workplane().rect(L - 12, W - 12, forConstruction=True).vertices().hole(2.5, 8.0))
base = base.union(posts)

# vent slots through one long wall
vents = (cq.Workplane("XZ").workplane(offset=-W / 2 - 1)
         .pushPoints([(x, H / 2) for x in (-15, -7.5, 0, 7.5, 15)])
         .slot2D(14, 2.0, 90).extrude(T + 2))
base = base.cut(vents)

EXPLODE = 18.0                                # lift the lid so the picture shows the inside; set 0 to close it
lid = (cq.Workplane("XY").workplane(offset=H + EXPLODE).rect(L, W).extrude(T)
       .edges("|Z").fillet(3.0)
       .faces(">Z").workplane().rect(L - 12, W - 12, forConstruction=True).vertices().cboreHole(2.8, 5.5, 1.2))

result = {"enclosure base": base, "enclosure lid": lid}
