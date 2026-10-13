"""Проверка геометрии 38 кадров stage7: пиксельная позиция каждого маркера.

Воспроизводит математику stage7_full.py: центр = union-bbox зон, fit_zoom, endpoint =
школа + (r/KMX)·(cos az, sin az) в plane-конвенции (az из CSV, 0°=восток).
Предсказанный пиксель: x = 400 + (elon-cx)/w_deg·800, y = 300 + (cy-elat)/(w_deg·0.75·cos(lat_c))·600
(вертикаль — планарно, cos на широте центра; эмпирически ±3%).
Сигнатура маркера в окне 25x25: белые пиксели (цифра) + синие пиксели кольца.
Компасный бэринг лепестка = (90 - az) mod 360.
Выход: reports/plots/stage7/geometry_check.json.
"""
import csv
import json
import math
import sys
import io
from pathlib import Path

import numpy as np
from PIL import Image
from shapely import from_geojson

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
SDIR = ROOT / "reports" / "plots" / "stage7"
KMX = 111.32

schools = {}
with open(ROOT / "config" / "schools.csv", encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        if r["selected"] == "1":
            schools[r["entity_id"]] = (r["name"], float(r["lat"]), float(r["lon"]))

zones_all = {}
for fn in ("car_zones.geojson", "pt_zones.geojson"):
    mode_key = "car" if fn.startswith("car") else "pt"
    d = json.loads((ROOT / "data" / "out" / fn).read_text(encoding="utf-8"))
    for feat in d["features"]:
        p = feat["properties"]
        zones_all.setdefault((mode_key, p["school_id"]), {})[int(p["min"])] = \
            from_geojson(json.dumps(feat["geometry"]))


def fit_zoom(bw, bh, px=800):
    need = max(bw, bh / 0.75) * 1.15
    for z in range(18, 0, -1):
        if 1125.0 / (2 ** z) >= need:
            return z
    return 1


def green_marker_px(img):
    r, g, b = img[:, :, 0].astype(int), img[:, :, 1].astype(int), img[:, :, 2].astype(int)
    m = (g > 130) & (g > r + 60) & (g > b + 60)
    # крупнейшая связная компонента (иначе зелёные POI-иконки утянут среднее)
    h, w = m.shape
    seen = np.zeros_like(m, dtype=bool)
    best_pts = []
    for y0 in range(h):
        for x0 in range(w):
            if not m[y0, x0] or seen[y0, x0]:
                continue
            q = [(x0, y0)]
            seen[y0, x0] = True
            pts = []
            while q:
                x, y = q.pop()
                pts.append((x, y))
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        nx, ny = x + dx, y + dy
                        if 0 <= nx < w and 0 <= ny < h and m[ny, nx] and not seen[ny, nx]:
                            seen[ny, nx] = True
                            q.append((nx, ny))
            if len(pts) > len(best_pts):
                best_pts = pts
    if len(best_pts) < 20:
        return None
    xs = [p[0] for p in best_pts]
    ys = [p[1] for p in best_pts]
    return (sum(xs) / len(xs), sum(ys) / len(ys))


def marker_signature(img, cx, cy, half=12):
    h, w, _ = img.shape
    x0, x1 = max(0, int(cx) - half), min(w, int(cx) + half + 1)
    y0, y1 = max(0, int(cy) - half), min(h, int(cy) + half + 1)
    if x1 <= x0 or y1 <= y0:
        return None
    crop = img[y0:y1, x0:x1].astype(int)
    r, g, b = crop[:, :, 0], crop[:, :, 1], crop[:, :, 2]
    white = ((r > 200) & (g > 200) & (b > 200)).sum()
    blue = ((b > 150) & (r < 100) & (g < 130) & (b > r + 80) & (b > g + 60)).sum()
    # «белая цифра на синем кольце»: белые пиксели, у которых есть синий сосед в 3px
    ring_white = 0
    wy, wx = np.where((r > 200) & (g > 200) & (b > 200))
    for i in range(len(wx)):
        x, y = wx[i], wy[i]
        xa, xb = max(0, x - 3), min(crop.shape[1], x + 4)
        ya, yb = max(0, y - 3), min(crop.shape[0], y + 4)
        if (blue_near := ((b[ya:yb, xa:xb] > 150) & (r[ya:yb, xa:xb] < 100)).any()):
            ring_white += 1
    return {"white": int(white), "blue": int(blue), "ring_white": int(ring_white)}


def main():
    frames = []
    with open(SDIR / "stage7_frames.csv", newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if r["mode"] in ("car", "pt") and r["school_id"] != "OVERVIEW":
                frames.append(r)
    out = {}
    for r in frames:
        sid, mode = r["school_id"], r["mode"]
        key = f"{mode}__{sid}"
        _n, lat0, lon0 = schools[sid]
        zz = zones_all[(mode, sid)]
        minx = min(z.bounds[0] for z in zz.values())
        miny = min(z.bounds[1] for z in zz.values())
        maxx = max(z.bounds[2] for z in zz.values())
        maxy = max(z.bounds[3] for z in zz.values())
        cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
        z_fit = fit_zoom(maxx - minx, maxy - miny)
        img = np.array(Image.open(SDIR / r["frame"]).convert("RGB"))
        gpx = green_marker_px(img)
        # часть кадров отрендерена с z-1 (ретрай out-of-bounds): выбираем z по зелёному маркеру
        best = None
        for z in (z_fit, z_fit - 1):
            w_deg = 1125.0 / 2 ** z
            v_deg = w_deg * 0.75 * math.cos(math.radians(cy))
            spx_pred = (400 + (lon0 - cx) / w_deg * 800,
                        300 + (cy - lat0) / v_deg * 600)
            dpx = math.hypot(gpx[0] - spx_pred[0], gpx[1] - spx_pred[1]) if gpx else None
            if best is None or (dpx is not None and dpx < best[1]):
                best = (z, dpx, spx_pred)
        z, dpx, spx_pred = best
        w_deg = 1125.0 / 2 ** z
        v_deg = w_deg * 0.75 * math.cos(math.radians(cy))
        raw = r["lobes"]
        if raw.startswith('"') and raw.endswith('"'):
            raw = raw[1:-1]
        lobes = json.loads(raw.replace('""', '"'))
        res = []
        for lb in lobes:
            az = float(lb["azimuth"])
            r_km = float(lb["r_max_km"])
            rad = math.radians(az)
            elon = lon0 + (r_km / KMX) * math.cos(rad)
            elat = lat0 + (r_km / KMX) * math.sin(rad)
            px = 400 + (elon - cx) / w_deg * 800
            py = 300 + (cy - elat) / v_deg * 600
            sig = marker_signature(img, px, py)
            res.append({
                "lobe_id": lb["lobe_id"], "number": lb["number"],
                "az_csv": az, "bearing_compass": round((90 - az) % 360, 1),
                "px": [round(px), round(py)], "sig": sig,
                "on_frame": 0 <= px < 800 and 0 <= py < 600,
            })
        # перекрытия маркеров
        for i, a in enumerate(res):
            md = min((math.hypot(a["px"][0] - b["px"][0], a["px"][1] - b["px"][1])
                      for j, b in enumerate(res) if j != i), default=999)
            a["nearest_marker_px"] = round(md, 1)
        out[key] = {"z": z, "cx": cx, "cy": cy, "green_px": gpx,
                    "school_px_pred": spx_pred, "school_dpx": round(dpx, 1) if dpx else None,
                    "lobes": res}
        ok = sum(1 for a in res if a["sig"] and a["sig"]["ring_white"] >= 4)
        print(f"{key:48s} z={z} green_dpx={dpx and round(dpx,1)} "
              f"sig_ok={ok}/{len(res)}")
    (SDIR / "geometry_check.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("написано: geometry_check.json")


if __name__ == "__main__":
    main()
