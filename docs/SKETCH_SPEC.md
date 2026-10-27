# Rolling oak slat cabinet: what the hand sketch says, and how it is modelled

Source: a hand-drawn sheet with a 3/4 view, front ("frontal"), lateral, top and bottom views, a dimension box
(24" x 24" x 22.5"), and an inset drawing of the hidden wheels. `build_cabinet()` models every item below; the
column "Certainty" says how sure the reading is.

| # | What the sketch shows | How it is modelled | Certainty |
|---|---|---|---|
| 1 | Overall 24" wide, 24" tall, 22.5" deep | `width`, `tower_h`, `depth` | stated |
| 2 | Vertical slats on all four faces (about 10 across front/back, 6 along each side) | `front_slats=10`, `side_slats=6`, 0.15" gaps, 1/2" oak | counted |
| 3 | One large circular scoop: the slat tops follow an arc from the two top corners to a low point in the middle | each front (and back) slat is an extruded profile whose top edge is a true circular arc (R = 21.0" for the default sag of 10") | high |
| 4 | Five strips from front to back in the top view (about 4 / 3.75 / 7.5 / 3.75 / 4 in) at three heights: 24, 19, 14, 19, 24 | five hinged lids at those heights; widths from the measured ratio (`section_widths` overrides) | high |
| 5 | Tilted blocks above the scoop in the 3/4 view | the lids drawn open; `open_deg=30` poses the four side lids open (hinged at the back) | medium |
| 6 | Dark squares on the two tall boxes | 1 3/4" square finger openings through the plywood front wall | medium |
| 7 | Dark wedges on the two step boxes | wedge-shaped openings (a right trapezoid) through the plywood front wall | medium |
| 8 | Slat panel stops above the floor; a band between the feet in the frontal and lateral views | oak apron on all four sides between the feet | high |
| 9 | Four L-shaped corner feet in plan view, each with a circle (wheel) inside | each foot is two oak walls forming an L plus a top plate; a swivel caster (plate, swivel, two fork plates, wheel) is hidden inside | high |
| 10 | Inset drawing: wheel mounted under a plate | caster plate screwed under the foot top plate; wheel clears the floor line by design | high |
| 11 | A framed panel of vertical bars under the scoop in the 3/4 view (a door in the middle of the front) | front door: the four centre slats on two oak battens, hinged on the left (2 butt hinges), push-to-open with a hidden magnetic latch so nothing shows on the front (`door_pull="bar"` adds a slim vertical pull instead), opening onto the centre compartment through a 6 3/4 in wide opening in the plywood front wall; `door=False` removes it, `door_open_deg=90` shows it open | medium |
| 12 | Small notch at the front of the top strip | half-round finger notch in the centre lid | low |

Not in the sketch (my engineering proposal, flagged in `project.notes`): the plywood carcass behind the slats, the
dividers, lid hinges (2 per lid), apron height, caster size, and the exact finger-opening shapes.

The other four compartments are reached through their lids; the sketch shows no other door.

Questions worth confirming with the designer before cutting wood: (a) is the scoop also cut in the back? (default
yes, `arc_on_back=False` for a plain back), (b) are the tilted blocks open lids, (c) do the dark squares/wedges mean
finger openings, and (d) how should the interior be organised.
