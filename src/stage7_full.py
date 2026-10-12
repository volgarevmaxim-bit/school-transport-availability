"""Стадия 7 (полная): static maps — карты зон pn + нумерованные маркеры лепестков.

Фреймы:
- на каждую (школа, режим) с лепестками: PNG 800x600, pn-полигоны зон (ВНЕШНЯЯ первой:
  сортировка min DESC), маркер школы (чёрный ~k:c), маркеры лепестков (нумерованные ~n:i).
- 2 обзорных кадра (car/ot): маркеры 20 школ, без полигонов.
Азимут лепестков — конвенция stage6: 0° = восток, +y = север (плоскость lon/lat).
Выход: reports/plots/stage7/<mode>/<school>.png, overview_<mode>.png, manifest stage7_frames.csv.
Аргумент: макс. число фреймов (тест-режим), по умолчанию все.
"""
import csv
import json
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from shapely import from_geojson
from client import static_map

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "reports" / "plots" / "stage7"
MANIFEST = OUT_DIR / "stage7_frames.csv"

KM_DEG = 111.32
MODE_LABEL = {"driving": "car", "public_transport": "pt"}
MODE_COLOR = {"driving": "2b7bba", "public_transport": "e6772e"}

schools = {}
with open(ROOT / "config" / "schools.csv", encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        if r["selected"] == "1":
            schools[r["entity_id"]] = (r["name"], float(r["lat"]), float(r["lon"]))


def load_zones(mode):
    fn = "car_zones.geojson" if mode == "driving" else "pt_zones.geojson"
    d = json.loads((ROOT / "data" / "out" / fn).read_text(encoding="utf-8"))
    out = {}
    for f in d["features"]:
        p = f["properties"]
        out.setdefault(p["school_id"], {})[int(p["min"])] = from_geojson(json.dumps(f["geometry"]))
    return out


def load_lobes(mode):
    fn = "lobes_car.csv" if mode == "driving" else "lobes_pt.csv"
    out = {}
    with open(ROOT / "data" / "out" / fn, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if r["mode"] != mode:
                continue
            out.setdefault(r["school_id"], []).append(r)
    for v in out.values():
        v.sort(key=lambda r: float(r["azimuth"]))
    return out


MAX_PN = 13000  # сырая суммарная длина pn; длиннее — 414 (Л2Ш 33K пойман 12.10)


def ring_pn(poly, color, fill, tol):
    g = poly.simplify(tol, preserve_topology=True)
    if g.geom_type == "MultiPolygon":
        g = max(g.geoms, key=lambda p: p.area)
    coords = [f"{y:.5f},{x:.5f}" for x, y in g.exterior.coords]
    return ",".join(coords) + f"~c:{color}~f:{fill}"


def fit_zoom(bbox_w_deg, bbox_h_deg, px=800):
    """Зум под bbox с учётом высоты вьюпорта (600/800 ширины) и запаса 15%."""
    need = max(bbox_w_deg, bbox_h_deg / 0.75) * 1.15
    for z in range(18, 0, -1):
        if 1125.0 / (2 ** z) >= need:
            return z
    return 1


def lobe_endpoint(sid, az_deg, r_km):
    lat0, lon0 = schools[sid][1], schools[sid][2]
    rad = math.radians(az_deg)
    dx = (r_km / KM_DEG) * math.cos(rad)
    dy = (r_km / KM_DEG) * math.sin(rad)
    return lon0 + dx, lat0 + dy


def main():
    max_frames = int(sys.argv[1]) if len(sys.argv) > 1 else None
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = []

    for mode, label in (("driving", "car"), ("public_transport", "pt")):
        zones = load_zones(mode)
        lobes = load_lobes(mode)
        out_sub = OUT_DIR / label
        out_sub.mkdir(exist_ok=True)
        print(f"\n=== {label}: школ с лепестками {len(lobes)} ===")

        for sid in lobes:
            if max_frames is not None and len(manifest) >= max_frames:
                print("тест-лимит достигнут")
                return
            if sid not in zones:
                print(f"  ПРОПУСК {sid}: нет зон")
                continue
            zmins = sorted(zones[sid], reverse=True)  # внешняя первой
            # bbox/центр/зум — по ОБЪЕДИНЕНИЮ всех зон кадра (у 2007-фмш pt 20-мин зона вне bbox 40-мин)
            minx = min(z.bounds[0] for z in zones[sid].values())
            miny = min(z.bounds[1] for z in zones[sid].values())
            maxx = max(z.bounds[2] for z in zones[sid].values())
            maxy = max(z.bounds[3] for z in zones[sid].values())
            cx = (minx + maxx) / 2
            cy = (miny + maxy) / 2
            z = fit_zoom(maxx - minx, maxy - miny)
            tol_cands = (0.006, 0.01, 0.02) if mode == "driving" else (0.001, 0.002, 0.004)
            pns = None
            for tol in tol_cands:
                # каждый полигон — отдельный pn (свой цвет); порядок: внешняя (40) первой — нижний слой
                pns = [ring_pn(zones[sid][m], MODE_COLOR[mode], MODE_COLOR[mode] + "33", tol)
                       for m in zmins]
                if sum(len(p) for p in pns) <= MAX_PN or tol == tol_cands[-1]:
                    break
            lat0, lon0 = schools[sid][1], schools[sid][2]
            mks = [f"{lat0},{lon0}~k:c~s:l~c:gn"]  # школа — зелёный крупный кружок
            order = []
            for i, lb in enumerate(lobes[sid], start=1):
                elon, elat = lobe_endpoint(sid, float(lb["azimuth"]), float(lb["r_max_km"]))
                mks.append(f"{elat},{elon}~k:c~n:{i}")  # нумерованный, цвет по умолчанию (синий)
                order.append({"number": i, "lobe_id": lb["lobe_id"], "azimuth": lb["azimuth"],
                              "r_max_km": lb["r_max_km"], "min": lb["min"]})
            r = static_map(f"{cy},{cx}", zoom=z, size="800x600",
                           markers=mks, polygons=pns)
            # «out of bounds» при узком вьюпорте: сервер мерит в меркаторе (h/cos(lat)).
            # Ретрай один раз с зумом на 1 ниже (центр тот же, вьюпорт 2×).
            if r["status"] == 400 and z > 1:
                r = static_map(f"{cy},{cx}", zoom=z - 1, size="800x600",
                               markers=mks, polygons=pns)
                if r["status"] == 200:
                    z -= 1
            fn = out_sub / f"{sid}.png"
            ok = r["status"] == 200 and isinstance(r["data"], bytes)
            if ok:
                fn.write_bytes(r["data"])
            print(f"  {sid[:40]:42s} z={z} зоны={zmins} лепестки={len(lobes[sid])} "
                  f"pn={sum(len(p) for p in pns)}с tol={tol} -> {r['status']} "
                  f"{len(r['data']) if ok else str(r['data'])[:80]}")
            manifest.append({"frame": str(fn.relative_to(OUT_DIR)), "school_id": sid,
                             "mode": label, "status": r["status"],
                             "lobes": json.dumps(order, ensure_ascii=False)})
            time.sleep(2.5)  # запас против per-minute лимитов static (~24/мин)

        # ---- обзорный кадр ----
        lons = [s[2] for s in schools.values()]
        lats = [s[1] for s in schools.values()]
        cx = (min(lons) + max(lons)) / 2
        cy = (min(lats) + max(lats)) / 2
        z = fit_zoom(max(lons) - min(lons), max(lats) - min(lats))
        mk = [f"{lat},{lon}~k:c" for _n, lat, lon in schools.values()]
        r = static_map(f"{cy},{cx}", zoom=z, size="800x600", markers=mk)
        fn = OUT_DIR / f"overview_{label}.png"
        if r["status"] == 200 and isinstance(r["data"], bytes):
            fn.write_bytes(r["data"])
        print(f"  обзор {label}: z={z} -> {r['status']} "
              f"{len(r['data']) if isinstance(r['data'], bytes) else str(r['data'])[:80]}")
        manifest.append({"frame": str(fn.relative_to(OUT_DIR)), "school_id": "OVERVIEW",
                         "mode": label, "status": r["status"], "lobes": "[]"})
        time.sleep(2.5)

    with open(MANIFEST, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["frame", "school_id", "mode", "status", "lobes"])
        w.writeheader()
        w.writerows(manifest)
    print(f"\nфреймов: {len(manifest)}, манифест: {MANIFEST}")


if __name__ == "__main__":
    main()
