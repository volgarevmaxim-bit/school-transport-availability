"""Стадия 7: контроль порядка отрисовки pn-полигонов (20-мин синяя ПОД 40-мин оранжевой?).

Проба 2 = blue20 + orange40 (обе). Проба 3 = только blue20. Проба 4 = только orange40.
Тот же вьюпорт (центр/зум из пробы 2). Попиксельное сравнение внутри 20-мин полигона
и на его границе: видна ли синяя в пробе 2 (наложение/порядок/бленд).
"""
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from shapely import from_geojson
from PIL import Image
from client import static_map

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "reports" / "plots"
L2SH = "лицей-вторая-школа-в-ф-овчинникова"
COLORS = {20: "2b7bba", 40: "e6772e"}
CX, CY, Z = 55.72149, 37.45739, 10      # вьюпорт пробы 2
SIZE = (800, 600)


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
    return ",".join(f"{y:.5f},{x:.5f}" for x, y in g.exterior.coords) + f"~c:{color}~f:{fill}"


def wpx(lat, lon, z):
    n = 2 ** z
    x = (lon + 180) / 360 * 256 * n
    y = (1 - math.log(math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat))) / math.pi) / 2 * 256 * n
    return x, y


polys = zone_polys(L2SH)
pn_blue = ring_pn(polys[20], COLORS[20], COLORS[20] + "44")
pn_orange = ring_pn(polys[40], COLORS[40], COLORS[40] + "44")

r3 = static_map(f"{CX},{CY}", zoom=Z, size="800x600", polygons=pn_blue)
r4 = static_map(f"{CX},{CY}", zoom=Z, size="800x600", polygons=pn_orange)
print("проба 3 (blue only):", r3["status"], "| байт:", len(r3["data"]) if isinstance(r3["data"], bytes) else r3["data"][:120])
print("проба 4 (orange only):", r4["status"], "| байт:", len(r4["data"]) if isinstance(r4["data"], bytes) else r4["data"][:120])

if not (isinstance(r3["data"], bytes) and isinstance(r4["data"], bytes)):
    sys.exit("одна из проб не 200 — стоп")

(OUT_DIR / "stage7_probe3_blue20_only.png").write_bytes(r3["data"])
(OUT_DIR / "stage7_probe4_orange40_only.png").write_bytes(r4["data"])

im2 = Image.open(OUT_DIR / "stage7_probe2_l2sh_car20_40.png").convert("RGB")
im3 = Image.open(OUT_DIR / "stage7_probe3_blue20_only.png").convert("RGB")
im4 = Image.open(OUT_DIR / "stage7_probe4_orange40_only.png").convert("RGB")
wcx, wcy = wpx(CX, CY, Z)


def screen(lat, lon):
    x, y = wpx(lat, lon, Z)
    return int(x - wcx + 400), int(y - wcy + 300)


def mean_diff(im_a, im_b, points):
    d = [sum(abs(a - b) for a, b in zip(im_a.getpixel(p), im_b.getpixel(p))) for p in points]
    return sum(d) / len(d)


# сетки точек: внутри 20-мин (гексагональная сетка от центра), на границе 20-мин, в «только 40»
p20 = polys[20]
cx0, cy0 = p20.centroid.x, p20.centroid.y
inside, boundary = [], []
for i in range(-8, 9):
    for j in range(-8, 9):
        lat = cy0 + j * 0.008
        lon = cx0 + i * 0.010
        if i == 0 and j == 0:
            continue
        from shapely.geometry import Point
        pt = Point(lon, lat)
        if p20.contains(pt):
            inside.append(screen(lat, lon))
        elif p20.boundary.distance(pt) < 0.004:
            boundary.append(screen(lat, lon))
print(f"\nвнутри 20-мин: {len(inside)} точек, у границы: {len(boundary)} точек")
print(f"средн. |Δ| внутри: C-vs-A(blue) = {mean_diff(im2, im3, inside):.1f} | C-vs-B(orange) = {mean_diff(im2, im4, inside):.1f}")
print(f"средн. |Δ| у границы: C-vs-A = {mean_diff(im2, im3, boundary):.1f} | C-vs-B = {mean_diff(im2, im4, boundary):.1f}")
print(f"\nинтерпретация: C=обе, A=только синяя, B=только оранжевая")
print("  внутри: C≈A → оранжевая не рисуется внутри; C≈B → синяя скрыта оранжевой; C темнее обоих → бленд")
print("  граница: C≠B и C≠A → оба контура видны; C≈B → синяя граница скрыта")
