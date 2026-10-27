"""Cut list, board-foot and sheet-area estimates from a Project."""
from __future__ import annotations

import csv
import io
from collections import OrderedDict

from .model import Project, SHEET, SOLID, frac


def _q(x: float) -> float:
    """Quantise to 1/32 in so near-identical parts group together."""
    return round(x * 32) / 32


def cutlist(project: Project) -> list[dict]:
    groups: "OrderedDict[tuple, dict]" = OrderedDict()
    for b in project.boards:
        key = (b.material, _q(b.thickness), _q(b.width), _q(b.length))
        g = groups.setdefault(key, {"material": b.material, "thickness": key[1], "width": key[2],
                                    "length": key[3], "qty": 0, "parts": []})
        g["qty"] += 1
        g["parts"].append(b.name)
    rows = sorted(groups.values(), key=lambda r: (r["material"], -r["thickness"], -r["length"], -r["width"]))
    for r in rows:
        kind = project.materials.get(r["material"], {}).get("kind", SOLID)
        r["kind"] = kind
        r["label"] = project.materials.get(r["material"], {}).get("label", r["material"])
    return rows


def board_feet(rows: list[dict], waste: float = 0.15) -> dict:
    net = sum(r["qty"] * r["thickness"] * r["width"] * r["length"] / 144 for r in rows if r["kind"] == SOLID)
    return {"net_bf": round(net, 2), "waste_pct": int(waste * 100), "buy_bf": round(net * (1 + waste), 1)}


def sheet_area_sqft(rows: list[dict]) -> float:
    return round(sum(r["qty"] * r["width"] * r["length"] / 144 for r in rows if r["kind"] == SHEET), 2)


def to_markdown(project: Project) -> str:
    rows = cutlist(project)
    bf = board_feet(rows)
    L = [f"# Cut list: {project.name}", "",
         "| Qty | Material | T | W | L | Parts |", "|---:|---|---:|---:|---:|---|"]
    for r in rows:
        parts = ", ".join(r["parts"][:3]) + (f" +{len(r['parts']) - 3} more" if len(r["parts"]) > 3 else "")
        L.append(f"| {r['qty']} | {r['label']} | {frac(r['thickness'])} | {frac(r['width'])} | {frac(r['length'])} | {parts} |")
    L += ["", f"**Solid lumber:** {bf['net_bf']} board feet net, buy about {bf['buy_bf']} bf "
              f"(+{bf['waste_pct']}% waste).",
          f"**Sheet goods:** {sheet_area_sqft(rows)} sq ft net (see the nesting layout for sheets to buy)."]
    if project.hardware:
        L += ["", "## Hardware", "", "| Qty | Item | For |", "|---:|---|---|"]
        agg: "OrderedDict[tuple, int]" = OrderedDict()
        for h in project.hardware:
            k = (h["item"], h.get("for", ""))
            agg[k] = agg.get(k, 0) + int(h.get("qty", 1))
        for (item, use), q in agg.items():
            L.append(f"| {q} | {item} | {use} |")
    if project.notes:
        L += ["", "## Notes", ""] + [f"- {n}" for n in project.notes]
    return "\n".join(L) + "\n"


def to_csv(project: Project) -> str:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["qty", "material", "thickness_in", "width_in", "length_in", "parts"])
    for r in cutlist(project):
        w.writerow([r["qty"], r["label"], r["thickness"], r["width"], r["length"], "; ".join(r["parts"])])
    return out.getvalue()
