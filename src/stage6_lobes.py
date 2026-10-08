"""Стадия 6 (ОТ): детекция лепестков доступности по радиальным профилям.

Локально, 0 запросов API. Для каждого полигона: радиальный профиль r(θ) (сектора 5°),
порог медиана + k·MAD (k из config). Лепесток = связная группа секторов выше порога
(допуск разрыва 1 сектор), шириной ≥2 секторов. Метрики: азимут центра (взвешенный по r),
ширина, r_max, площадь клина, вытянутость. Выход: lobes_pt.csv, lobes_pt.geojson, полярные
графики reports/plots/profiles_pt/.
"""
import csv
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import yaml
from shapely.geometry import LineString, MultiPoint, Point, Polygon
from shapely import from_geojson
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
CFG = yaml.safe_load((ROOT / "config" / "experiment.yaml").read_text(encoding="utf-8"))
K_MAD = CFG["lobes"]["k_mad"]
SECTOR = CFG["lobes"]["sector_deg"]
ZONES = json.loads((ROOT / "data" / "out" / "pt_zones.geojson").read_text(encoding="utf-8"))

schools = {}
with open(ROOT / "config" / "schools.csv", encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        if r["selected"] == "1":
            schools[r["entity_id"]] = (float(r["lat"]), float(r["lon"]))

PROF_DIR = ROOT / "reports" / "plots" / "profiles_pt"
PROF_DIR.mkdir(parents=True, exist_ok=True)

KMX = 111.32  # км/градус по долготе на широте (для метрик км)


def radial_profile(poly, spt, step=SECTOR, r_deg=0.6):
    prof = {}
    for a in range(0, 360, step):
        rad = math.radians(a)
        end = Point(spt.x + r_deg * math.cos(rad), spt.y + r_deg * math.sin(rad))
        ray = LineString([spt, end])
        inter = poly.boundary.intersection(ray)
        if inter.is_empty:
            prof[a] = 0.0
            continue
        pts = [inter] if isinstance(inter, Point) else list(inter.geoms)
        prof[a] = max(spt.distance(p) for p in pts)
    return prof


def median(xs):
    s = sorted(xs)
    return s[len(s) // 2]


def smooth_profile(prof, w=3):
    """Скользящее среднее по секторам (круговое) — против одиночных спайков."""
    angs = sorted(prof)
    n = len(angs)
    half = w // 2
    out = {}
    for i, a in enumerate(angs):
        out[a] = sum(prof[angs[(i + j) % n]] for j in range(-half, half + 1)) / w
    return out


def lobes_from_profile(prof, k=K_MAD, min_sectors=2):
    vals = [v for v in prof.values() if v > 0]
    if not vals:
        return []
    med = median(vals)
    mad = median([abs(v - med) for v in vals]) or 1e-12
    thr = med + k * mad
    cand = [a for a in sorted(prof) if prof[a] > thr]
    # связные группы с допуском разрыва в 1 сектор
    groups, cur = [], []
    prev = None
    for a in cand:
        if cur and a - prev > SECTOR * 2:  # разрыв > 1 сектора
            groups.append(cur); cur = []
        cur.append(a)
        prev = a
    if cur:
        groups.append(cur)
    lobes = []
    for g in groups:
        if len(g) < min_sectors:
            continue
        w = sum(prof[a] for a in g)
        az = sum(a * prof[a] for a in g) / w if w else g[0]
        lobes.append({"angles": g, "azimuth": az % 360, "width_deg": len(g) * SECTOR,
                      "r_max": max(prof[a] for a in g), "thr": thr, "med": med, "mad": mad})
    return lobes


def lobe_wedge(spt, prof, angles):
    """Клин лепестка: от школы до границы по крайним секторам (профиль — в plane-градусах)."""
    edges = sorted(angles)
    a0 = edges[0] - SECTOR / 2
    a1 = edges[-1] + SECTOR / 2
    ring = [spt]
    n = max(2, len(edges))
    for i in range(n + 1):
        a = a0 + (a1 - a0) * i / n
        rad = math.radians(a)
        r = prof[edges[min(i, len(edges) - 1)]]
        ring.append(Point(spt.x + r * math.cos(rad), spt.y + r * math.sin(rad)))
    return Polygon(ring)


def lobe_metrics(poly, wedge, lat):
    """Площадь клипа, вытянутость через oriented bounding box, доля зоны."""
    clip = poly.intersection(wedge)
    if clip.is_empty:
        return 0.0, 0.0, 0.0
    area = clip.area * KMX * KMX * math.cos(math.radians(lat))
    mrr = clip.minimum_rotated_rectangle
    coords = list(mrr.exterior.coords)[:4]
    w = Point(coords[0]).distance(Point(coords[1]))
    h = Point(coords[1]).distance(Point(coords[2]))
    width_km = min(w, h) * KMX
    length_km = max(w, h) * KMX
    return area, length_km / max(width_km, 1e-9), width_km


rows, feats = [], []
per_school = {sid: {"20": None, "40": None} for sid in schools}

for feat in ZONES["features"]:
    p = feat["properties"]
    sid, minutes = p["school_id"], p["min"]
    if sid not in schools:
        continue
    lat, lon = schools[sid]
    spt = Point(lon, lat)
    poly = from_geojson(json.dumps(feat["geometry"]))
    prof = radial_profile(poly, spt)
    prof_s = smooth_profile(prof)
    per_school[sid][str(minutes)] = (prof, prof_s, poly, spt, lat)

    lobes = lobes_from_profile(prof_s)
    zone_area_km2 = poly.area * KMX * KMX * math.cos(math.radians(lat))
    for i, lb in enumerate(lobes):
        # r_max по СЫРОМУ профилю в секторах лепестка (сглаженный занижает пик)
        raw_rmax = max(prof[a] for a in lb["angles"])
        wedge = lobe_wedge(spt, prof, lb["angles"])
        area, elong, width_km = lobe_metrics(poly, wedge, lat)
        rows.append({
            "lobe_id": f"{sid[:20]}-pt{minutes}-{i+1}", "school_id": sid,
            "mode": "public_transport", "min": minutes,
            "azimuth": round(lb["azimuth"], 1), "width_deg": lb["width_deg"],
            "r_max_km": round(raw_rmax * KMX, 2), "area_km2": round(area, 2),
            "elongation": round(elong, 1),
            "zone_share": round(area / max(zone_area_km2, 1e-9), 4),
            "thr_km": round(lb["thr"] * KMX, 2), "k_mad": K_MAD, "suspicious": "",
        })
        feats.append({"type": "Feature", "properties": rows[-1],
                      "geometry": json.loads(json.dumps(poly.intersection(wedge).__geo_interface__))})

# полярные графики по школам
for sid, d in per_school.items():
    fig, axes = plt.subplots(1, 2, subplot_kw={"projection": "polar"}, figsize=(10, 5.2))
    for ax, minutes in zip(axes, (20, 40)):
        if d[str(minutes)] is None:
            continue
        prof, prof_s, poly, spt, lat = d[str(minutes)]
        ang = [math.radians(a) for a in sorted(prof)]
        vals = [prof[a] * KMX for a in sorted(prof)]
        vals_s = [prof_s[a] * KMX for a in sorted(prof)]
        med = median(vals_s)
        thr = median([abs(v - med) for v in vals_s]) * K_MAD + med if vals_s else 0
        ax.plot(ang + [ang[0]], vals + [vals[0]], lw=0.8, color="#8899bb", alpha=0.7)
        ax.plot(ang + [ang[0]], vals_s + [vals_s[0]], lw=1.2, color="#2233aa")
        ax.plot(ang + [ang[0]], [thr] * (len(ang) + 1), ls="--", lw=1, color="#cc2222")
        for lb in lobes_from_profile(prof_s):
            aa = [math.radians(a) for a in lb["angles"]]
            vv = [prof[a] * KMX for a in lb["angles"]]
            ax.fill_between(aa, 0, vv, alpha=0.35, color="#ee6600")
        ax.set_title(f"{minutes} мин, порог {thr:.1f} км", fontsize=9)
        ax.set_theta_zero_location("N")
    fig.suptitle(f"{sid[:40]} — ОТ, радиальный профиль (оранж = лепестки)", fontsize=10)
    fig.tight_layout()
    fig.savefig(PROF_DIR / f"{sid[:60]}.png", dpi=100)
    plt.close(fig)

out_csv = ROOT / "data" / "out" / "lobes_pt.csv"
with open(out_csv, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["lobe_id"])
    w.writeheader()
    w.writerows(rows)
out_geo = ROOT / "data" / "out" / "lobes_pt.geojson"
out_geo.write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False), encoding="utf-8")

print(f"лепестков: {len(rows)}")
by_min = {}
for r in rows:
    by_min.setdefault(r["min"], []).append(r)
for m, rs in sorted(by_min.items()):
    print(f"  {m}-мин зоны: {len(rs)} лепестков")
print("топ-12 по вытянутости:")
for r in sorted(rows, key=lambda x: -x["elongation"])[:12]:
    print(f"  {r['lobe_id']:32} аз={r['azimuth']:6.1f}° ш={r['width_deg']:3}° r={r['r_max_km']:5.2f}км "
          f"выт={r['elongation']:5.1f} доля={r['zone_share']:.3f}")
print("CSV:", out_csv)
print("GeoJSON:", out_geo)
print("графики:", PROF_DIR)
