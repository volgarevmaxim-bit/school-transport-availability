"""Стадия 7 (проба): static maps с РЕАЛЬНЫМ полигоном зоны (pn) → PNG.

Проба 1: Л2Ш car 20-мин (одна зона + маркер школы).
Проба 2: Л2Ш car 20 + 40 (два вложенных полигона в одном pn-параметре, разделитель ~).
Вопросы пробы: лимит длины URL/вершин pn, 200-й ответ, корректная отрисовка (vision-проверка).
Зумирование: подбор z по ширине bbox полигона (эвристика 1125/2^z градусов на 800px).
"""
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from shapely import from_geojson
from client import static_map

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "reports" / "plots"
L2SH = "лицей-вторая-школа-в-ф-овчинникова"
SCHOOL_PT = (55.6979, 37.5564)          # Л2Ш, ул. Фотиевой 18 (schools.csv)
COLORS = {20: "2b7bba", 40: "e6772e"}   # цвета вьюера


def zone_polys(sid):
    zones = json.loads((ROOT / "data" / "out" / "car_zones.geojson").read_text(encoding="utf-8"))
    out = {}
    for f in zones["features"]:
        p = f["properties"]
        if p["school_id"] == sid and p["min"] in (20, 40):
            out[p["min"]] = from_geojson(json.dumps(f["geometry"]))
    return out


def ring_pn(poly, color, fill, tol=0.002):
    g = poly.simplify(tol, preserve_topology=True)
    if g.geom_type == "MultiPolygon":
        g = max(g.geoms, key=lambda p: p.area)
    coords = [f"{y:.5f},{x:.5f}" for x, y in g.exterior.coords]
    return ",".join(coords) + f"~c:{color}~f:{fill}"


def fit_zoom(bbox_w_deg, px=800):
    for z in range(18, 0, -1):
        if 1125.0 / (2 ** z) >= bbox_w_deg * 1.15:
            return z
    return 1


polys = zone_polys(L2SH)
print("зоны Л2Ш (car):", {m: round(p.area * 110.57 * 77.0, 1) for m, p in polys.items()}, "км² ≈")

p20 = polys[20]
minx, miny, maxx, maxy = p20.bounds
cx, cy = (miny + maxy) / 2, (minx + maxx) / 2
z = fit_zoom(maxx - minx)
print(f"центр {cx:.5f},{cy:.5f} зум {z} bbox-ширина {maxx - minx:.4f}°")

# ---- проба 1: одна зона ----
pn1 = ring_pn(p20, COLORS[20], COLORS[20] + "44")
print(f"pn-длина (20м, tol 0.002): {len(pn1)} символов")
r1 = static_map(f"{cx},{cy}", zoom=z, size="800x600",
                markers=f"{SCHOOL_PT[0]},{SCHOOL_PT[1]}~k:c",
                polygons=pn1)
print("проба 1:", r1["status"], "| cached:", r1.get("cached"), "| байт:", len(r1["data"]) if isinstance(r1["data"], bytes) else str(r1["data"])[:150])
if r1["status"] == 200 and isinstance(r1["data"], bytes):
    (OUT_DIR / "stage7_probe1_l2sh_car20.png").write_bytes(r1["data"])

# ---- проба 2: две вложенные зоны (20 + 40); зум/центр — по БОЛЬШЕМУ полигону (иначе «out of bounds») ----
p40 = polys[40]
minx2, miny2, maxx2, maxy2 = p40.bounds
cx2, cy2 = (miny2 + maxy2) / 2, (minx2 + maxx2) / 2
z2 = fit_zoom(maxx2 - minx2)
print(f"проба 2: центр {cx2:.5f},{cy2:.5f} зум {z2}")
pn2a = ring_pn(p20, COLORS[20], COLORS[20] + "44")
pn2b = ring_pn(p40, COLORS[40], COLORS[40] + "44")
pn2 = pn2a + "~" + pn2b
print(f"pn-длина (20+40): {len(pn2)} символов")
r2 = static_map(f"{cx2},{cy2}", zoom=z2, size="800x600",
                markers=f"{SCHOOL_PT[0]},{SCHOOL_PT[1]}~k:c",
                polygons=pn2)
print("проба 2:", r2["status"], "| cached:", r2.get("cached"), "| байт:", len(r2["data"]) if isinstance(r2["data"], bytes) else str(r2["data"])[:150])
if r2["status"] == 200 and isinstance(r2["data"], bytes):
    (OUT_DIR / "stage7_probe2_l2sh_car20_40.png").write_bytes(r2["data"])

print("\nPNG:", OUT_DIR)
