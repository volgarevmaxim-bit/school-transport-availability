"""Стадия 4 (урезана владельцем 08.10): только T_in (точка→школа) для оценки ошибки направления ОТ.

3 школы × 15 точек = 45 pt-запросов (суточный лимит routing_api 50−5=45 — ровно).
Точки на границах зон из pt_zones.geojson (ЛОКАЛЬНО, 0 изохронных запросов):
20-мин зона — 10 азимутов (0,36,...,324), 40-мин — 5 азимутов (0,72,...,288).
T_in: выезд с границы так, чтобы прибыть к 8:30 (старт = 8:30 − порог зоны).
Метрика: T_in vs порог зоны (1200/2400 с); доля T_in > порога — признак завышения зоны.

Метро-проба: ПЕРВЫЙ запрос дня идёт с transport[] включая metro — если 400, это и есть
ответ «pt/2.0 metro не принимает»; повтор той же точки без metro (400 в суточный счётчик
200-х не попадает). Ошибки 400 кэшем не перекрываются (client.py кэширует только 200).
"""
import csv
import json
import math
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import yaml
from shapely.geometry import LineString, Point
from client import public_transport_route, msk_to_unix, QuotaExhaustedError

ROOT = Path(__file__).resolve().parent.parent
CFG = yaml.safe_load((ROOT / "config" / "experiment.yaml").read_text(encoding="utf-8"))
DATE = CFG["date"]
DB = ROOT / "data" / "db" / "experiments.sqlite"

IDS = ["лицей-вторая-школа-в-ф-овчинникова", "школа-1532", "школа-2007-фмш"]
ARRIVAL = "08:30"
ANGLES_20 = list(range(0, 360, 36))   # 10 точек
ANGLES_40 = list(range(0, 360, 72))   # 5 точек

ZONES = json.loads((ROOT / "data" / "out" / "pt_zones.geojson").read_text(encoding="utf-8"))

schools = {}
with open(ROOT / "config" / "schools.csv", encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        if r["selected"] == "1":
            schools[r["entity_id"]] = (r["name"], float(r["lat"]), float(r["lon"]))


def log_probe(school, hyp, t):
    con = sqlite3.connect(DB)
    con.execute("INSERT INTO probes(school_id, mode, hypothesis, t_sec, method_version) VALUES(?,?,?,?,?)",
                (school, "pt", hyp, t, "v1"))
    con.commit()
    con.close()


def zone_poly(sid, minutes):
    for f in ZONES["features"]:
        p = f["properties"]
        if p["school_id"] == sid and p["min"] == minutes:
            from shapely import from_geojson
            return from_geojson(json.dumps(f["geometry"]))
    return None


def boundary_by_azimuth(poly, spt, angles, r_deg=0.6):
    out = {}
    for a in angles:
        rad = math.radians(a)
        end = Point(spt.x + r_deg * math.cos(rad), spt.y + r_deg * math.sin(rad))
        ray = LineString([spt, end])
        inter = poly.boundary.intersection(ray)
        if inter.is_empty:
            out[a] = None
            continue
        pts = [inter] if isinstance(inter, Point) else [g for g in inter.geoms]
        out[a] = min(pts, key=lambda p: spt.distance(p))
    return out


def km(spt, p):
    return spt.distance(p) * 111.32 * math.cos(math.radians(spt.y))


def pt_duration(lonlat_a, lonlat_b, start_unix, transports):
    r = public_transport_route(lonlat_a, lonlat_b, start_time_unix=start_unix,
                               enable_schedule=True, transports=transports)
    if r["status"] != 200:
        return None, r["status"], None
    data = r["data"]
    if isinstance(data, dict):          # 200, но ошибка в теле
        return None, f"200-dict: {str(data)[:120]}", None
    if not isinstance(data, list) or not data:
        return None, "200-empty", None  # маршрута нет
    return data[0]["total_duration"], 200, r.get("request_hash")


def point_str(p):
    return f"{p.x:.6f},{p.y:.6f}"


rows = []
transport_state = {"list": ["metro", "bus", "trolleybus", "tram"],
                   "metro_note": None, "n_queries": 0}
ARR_UNIX = msk_to_unix(DATE, ARRIVAL)

try:
    for sid in IDS:
        name, lat, lon = schools[sid]
        spt = Point(lon, lat)
        print(f"\n=== {name[:36]} ===")
        for minutes, angles in ((20, ANGLES_20), (40, ANGLES_40)):
            poly = zone_poly(sid, minutes)
            if poly is None:
                print(f"  {minutes}м: зона не найдена в pt_zones.geojson — пропуск")
                continue
            pts = boundary_by_azimuth(poly, spt, angles)
            for a, p in pts.items():
                if p is None:
                    print(f"  {minutes}м аз{a:3}°: нет пересечения границы"); continue
                pll = point_str(p)
                in_start = ARR_UNIX - minutes * 60
                t, st, h = pt_duration(pll, f"{lon},{lat}", in_start, transport_state["list"])
                transport_state["n_queries"] += 1
                if st == 400 and transport_state["metro_note"] is None:
                    transport_state["metro_note"] = ("pt/2.0: transport[] с metro → HTTP 400 — metro "
                                                     "НЕ принимается")
                    transport_state["list"] = ["bus", "trolleybus", "tram"]
                    print("  МЕТРО-ПРОБА: 400 с metro → переключаюсь на [bus,trolleybus,tram], повтор")
                    t, st, h = pt_duration(pll, f"{lon},{lat}", in_start, transport_state["list"])
                    transport_state["n_queries"] += 1
                if t is None:
                    print(f"  {minutes}м аз{a:3}°: status={st}"); continue
                log_probe(sid, f"in-{minutes}", t)
                over = int(t > minutes * 60)
                rows.append({"school": sid, "school_name": name, "min": minutes, "azimuth": a,
                             "dist_km": round(km(spt, p), 2), "T_in": t,
                             "threshold": minutes * 60, "T_in_over_threshold": over})
                print(f"  {minutes}м аз{a:3}°: T_in={t}с порог={minutes*60}с "
                      f"{'>ПОРОГА' if over else 'ok'} d={km(spt,p):.2f}км")
except QuotaExhaustedError as e:
    print("СТОП по лимиту (429):", e)

out_csv = ROOT / "data" / "out" / "stage4_tin.csv"
with open(out_csv, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)

print("\n=== МЕТРИКИ T_in (точка→школа, прибытие 8:30) ===")
for sid in IDS:
    for m in (20, 40):
        sub = [r for r in rows if r["school"] == sid and r["min"] == m]
        if not sub:
            continue
        ts = sorted(r["T_in"] for r in sub)
        over = sum(r["T_in_over_threshold"] for r in sub)
        print(f"{sid[:30]:32} {m:2}м (n={len(sub)}): медиана {ts[len(ts)//2]}с, "
              f"макс {ts[-1]}с, T_in>порога {over}/{len(sub)}")
all_ts = sorted(r["T_in"] for r in rows)
over_all = sum(r["T_in_over_threshold"] for r in rows)
print(f"ВСЕГО (n={len(rows)}): медиана {all_ts[len(all_ts)//2]}с, макс {all_ts[-1]}с, "
      f"T_in>порога {over_all}/{len(rows)}")
print("метро-проба:", transport_state["metro_note"] or "metro принят (200) в transport[]")
print("pt-запросов сделано:", transport_state["n_queries"])
print("CSV:", out_csv)

# гистограмма T_in − порог
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
fig, axes = plt.subplots(1, 3, figsize=(14, 4.2), sharey=True)
for ax, sid in zip(axes, IDS):
    sub = [r["T_in"] - r["threshold"] for r in rows if r["school"] == sid]
    ax.hist([x / 60 for x in sub], bins=12, color="#4477aa")
    ax.axvline(0, color="#cc2222", ls="--", lw=1)
    ax.set_title(schools[sid][0][:30], fontsize=9)
    ax.set_xlabel("T_in − порог, мин")
axes[0].set_ylabel("точек")
fig.suptitle("Стадия 4 (T_in-only): фактическое время в пути с границы зоны vs порог", fontsize=11)
fig.tight_layout()
png = ROOT / "reports" / "plots" / "stage4_tin_hist.png"
fig.savefig(png, dpi=110)
print("гистограмма:", png)
