"""Cutting layouts: 2-D sheet nesting (plywood) and 1-D stock cutting (solid lumber)."""
from __future__ import annotations

from dataclasses import dataclass

from .model import Project, SHEET, SOLID


@dataclass
class Placed:
    name: str
    sheet: int
    x: float
    y: float
    w: float
    h: float
    rotated: bool


def nest_sheets(project: Project, sheet_w: float = 48.0, sheet_l: float = 96.0, kerf: float = 0.125,
                allow_rotate: bool = True) -> dict:
    """Shelf-based first-fit-decreasing packing of all sheet-good parts."""
    parts = []
    for b in project.boards:
        if project.materials.get(b.material, {}).get("kind") != SHEET:
            continue
        dims = sorted(b.size, reverse=True)[:2]          # drop the thickness
        parts.append((b.name, dims[1], dims[0]))          # (name, w, l) with w <= l
    for name, w, l in parts:
        if min(w, l) > min(sheet_w, sheet_l) or max(w, l) > max(sheet_w, sheet_l):
            raise ValueError(f"Part '{name}' ({w:.2f} x {l:.2f} in) does not fit on a {sheet_w} x {sheet_l} in sheet.")
    parts.sort(key=lambda t: -t[2])
    sheets: list[dict] = []        # each: {"shelves": [{"y","h","x"}], "used_h": float}
    placed: list[Placed] = []

    def try_place(sh, idx, name, w, h, rotated) -> bool:
        for shelf in sh["shelves"]:
            if h <= shelf["h"] + 1e-9 and shelf["x"] + w <= sheet_w + 1e-9:
                placed.append(Placed(name, idx, shelf["x"], shelf["y"], w, h, rotated))
                shelf["x"] += w + kerf
                return True
        if sh["used_h"] + h <= sheet_l + 1e-9 and w <= sheet_w + 1e-9:
            shelf = {"y": sh["used_h"], "h": h, "x": w + kerf}
            sh["shelves"].append(shelf)
            sh["used_h"] += h + kerf
            placed.append(Placed(name, idx, 0.0, shelf["y"], w, h, rotated))
            return True
        return False

    for name, w, l in parts:
        # default orientation: long side along the sheet length (keeps face grain along the length)
        options = [(w, l, False)] + ([(l, w, True)] if allow_rotate else [])
        done = False
        for idx, sh in enumerate(sheets):
            for pw, ph, rot in options:
                if try_place(sh, idx, name, pw, ph, rot):
                    done = True
                    break
            if done:
                break
        if not done:
            sheets.append({"shelves": [], "used_h": 0.0})
            for pw, ph, rot in options:
                if try_place(sheets[-1], len(sheets) - 1, name, pw, ph, rot):
                    break
    area = sum(p.w * p.h for p in placed)
    total = len(sheets) * sheet_w * sheet_l
    return {"sheets": len(sheets), "sheet_w": sheet_w, "sheet_l": sheet_l, "kerf": kerf,
            "utilization_pct": round(100 * area / total, 1) if total else 0.0,
            "placements": [p.__dict__ for p in placed]}


def nest_sheets_svg(result: dict, px_per_in: float = 6.0) -> str:
    sw, sl = result["sheet_w"], result["sheet_l"]
    n = result["sheets"]
    gap = 24
    W = int(n * (sw * px_per_in + gap) + gap)
    H = int(sl * px_per_in + 2 * gap + 20)
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
           'font-family="Helvetica, Arial, sans-serif">', f'<rect width="{W}" height="{H}" fill="white"/>']
    for s in range(n):
        ox = gap + s * (sw * px_per_in + gap)
        oy = gap + 16
        out.append(f'<text x="{ox}" y="{oy - 5}" font-size="12" fill="#222">Sheet {s + 1} - {sw:g} x {sl:g} in</text>')
        out.append(f'<rect x="{ox}" y="{oy}" width="{sw * px_per_in}" height="{sl * px_per_in}" fill="#f6f1e4" '
                   'stroke="#222" stroke-width="1.5"/>')
        for p in result["placements"]:
            if p["sheet"] != s:
                continue
            x, y = ox + p["x"] * px_per_in, oy + p["y"] * px_per_in
            w, h = p["w"] * px_per_in, p["h"] * px_per_in
            out.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" fill="#e2c98d" '
                       'stroke="#5a4a22" stroke-width="0.8"/>')
            if w > 26 and h > 12:
                out.append(f'<text x="{x + 3:.1f}" y="{y + 11:.1f}" font-size="8" fill="#3a2f12">{p["name"]}</text>')
    out.append("</svg>")
    return "\n".join(out)


def cut_lumber(project: Project, stock_len: float = 96.0, kerf: float = 0.125) -> dict:
    """1-D first-fit-decreasing: group solid parts by (thickness, width), cut lengths from stock boards."""
    groups: dict[tuple[float, float], list[tuple[str, float]]] = {}
    for b in project.boards:
        if project.materials.get(b.material, {}).get("kind") != SOLID:
            continue
        key = (round(b.thickness, 4), round(b.width, 4))
        groups.setdefault(key, []).append((b.name, b.length))
    result = []
    for (t, w), items in sorted(groups.items(), key=lambda kv: (-kv[0][0], -kv[0][1])):
        items.sort(key=lambda it: -it[1])
        boards: list[dict] = []
        for name, length in items:
            if length > stock_len + 1e-9:
                raise ValueError(f"Part '{name}' is {length:.2f} in long; stock boards are {stock_len:g} in.")
            for bd in boards:
                if bd["left"] >= length + kerf - 1e-9 or abs(bd["left"] - length) < 1e-9:
                    bd["cuts"].append((name, length))
                    bd["left"] -= length + kerf
                    break
            else:
                boards.append({"cuts": [(name, length)], "left": stock_len - length - kerf})
        used = sum(l for _, l in items)
        result.append({"thickness": t, "width": w, "stock_boards": len(boards), "stock_len": stock_len,
                       "waste_in": round(len(boards) * stock_len - used, 1),
                       "boards": [{"cuts": [(n, round(l, 3)) for n, l in bd["cuts"]],
                                   "offcut_in": round(max(bd["left"], 0), 2)} for bd in boards]})
    return {"groups": result, "total_stock_boards": sum(g["stock_boards"] for g in result)}
