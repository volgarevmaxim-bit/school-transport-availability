"""Стадия 4: оценка ошибки направления «от школы» вместо «к школе» для ОТ.

3 школы (центр Л2Ш / пояс 1532 / периферия 2007 ФМШ) × зоны 20 и 40 мин.
10/5 точек на границе по азимуту. T_out = школа→точка (старт 05:30Z, контроль ≈ порогу зоны);
T_in = точка→школа (старт 05:30Z − T_out, прибытие ≈ 8:30). Метрики: медиана/макс |T_in−T_out|/T_out,
доля точек с T_in > порога. Таблица + гистограмма. Порог решения — за владельцем.
"""
import csv
import math
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import yaml
from shapely.geometry import LineString, MultiPoint, Point
from shapely import wkt as shapely_wkt
from client import isochrone, public_transport_route, msk_to_unix, msk_to_utc

ROOT = Path(__file__).resolve().parent.parent
CFG = yaml.safe_load((ROOT / "config" / "experiment.yaml").read_text(encoding="utf-8"))
DATE = CFG["date"]
DB = ROOT / "data" / "db" / "experiments.sqlite"

schools = {}
with open(ROOT / "config" / "schools.csv", encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        if r["selected"] == "1":
            schools[r["entity_id"]] = (r["name"], float(r["lat"]), float(r["lon"]))

IDS = ["лицей-вторая-школа-в-ф-овчинникова", "школа-1532", "школа-2007-фмш"]
TRANSPORTS = ["metro", "bus", "trolleybus", "tram"]  # metro — ПРОВЕРИТЬ первым запросом дня
ARRIVAL = "08:30"
# Сокращение владельца (08.10): 3 школы × 6 точек = 18 точек × 2 = 36 pt + 1 проба = 37 ≤ 50/день
ANGLES_20 = [0, 90, 180, 270]   # 4 точки на 20-мин зоне (кардинальные азимуты)
ANGLES_40 = [0, 180]            # 2 точки на 40-мин зоне


def log_probe(school, hyp, t):
    con = sqlite3.connect(DB)
    con.execute("INSERT INTO probes(school_id, mode, hypothesis, t_sec, method_version) VALUES(?,?,?,?,?)",
                (school, "pt", hyp, t, "v1"))
    con.commit()
    con.close()


def pt_duration(lonlat_a, lonlat_b, start_unix):
    r = public_transport_route(lonlat_a, lonlat_b, start_time_unix=start_unix,
                               enable_schedule=True, transports=TRANSPORTS)
    if r["status"] != 200 or not isinstance(r["data"], list) or not r["data"]:
        return None, r["status"]
    return r["data"][0]["total_duration"], r["status"]


def pt_zones(lat, lon):
    r = isochrone(lat=lat, lon=lon, durations=[1200, 2400], transport="public_transport",
                  start_time=msk_to_utc(DATE, ARRIVAL))
    if r["status"] != 200 or not isinstance(r["data"], dict):
        raise RuntimeError(f"iso pt status={r['status']}")
    geoms = [shapely_wkt.loads(i["geometry"]) for i in r["data"].get("isochrones", [])]
    geoms.sort(key=lambda g: g.area)
    return geoms[0], geoms[1]  # меньшая = 20 мин, большая = 40 мин


def boundary_by_azimuth(poly, school_pt, angles_deg, r_deg=0.6):
    out = {}
    for a in angles_deg:
        rad = math.radians(a)
        end = Point(school_pt.x + r_deg * math.cos(rad), school_pt.y + r_deg * math.sin(rad))
        ray = LineString([school_pt, end])
        inter = poly.boundary.intersection(ray)
        if inter.is_empty:
            out[a] = None
            continue
        pts = [inter] if isinstance(inter, Point) else [g for g in inter.geoms]
        out[a] = min(pts, key=lambda p: school_pt.distance(p))
    return out


def km(school_pt, p):
    return school_pt.distance(p) * 111.32 * math.cos(math.radians(school_pt.y))


rows = []
print("проба transport list с metro...")
r_probe = public_transport_route("37.5437,55.6923", "37.55644,55.69799",
                                 start_time_unix=msk_to_unix(DATE, ARRIVAL), enable_schedule=True,
                                 transports=TRANSPORTS)
print("  статус:", r_probe["status"], "| альтернатив:", len(r_probe["data"]) if isinstance(r_probe["data"], list) else "-")
if r_probe["status"] == 200 and isinstance(r_probe["data"], list) and r_probe["data"]:
    print("  total_duration первой:", r_probe["data"][0]["total_duration"], "| transport:", r_probe["data"][0].get("transport"))

for sid in IDS:
    name, lat, lon = schools[sid]
    spt = Point(lon, lat)
    print(f"\n=== {name[:36]} ===")
    z20, z40 = pt_zones(lat, lon)
    for zone, minutes, angles in ((z20, 20, ANGLES_20), (z40, 40, ANGLES_40)):
        pts = boundary_by_azimuth(zone, spt, angles)
        for a, p in pts.items():
            if p is None:
                print(f"  {minutes}м азимут {a}°: нет пересечения"); continue
            pll = f"{p.x:.6f},{p.y:.6f}"
            out_t, st_out = pt_duration(f"{lon},{lat}", pll, msk_to_unix(DATE, ARRIVAL))
            if out_t is None:
                print(f"  {minutes}м азимут {a}°: T_out status={st_out}"); continue
            in_start = msk_to_unix(DATE, ARRIVAL) - out_t
            in_t, st_in = pt_duration(pll, f"{lon},{lat}", in_start)
            if in_t is None:
                print(f"  {minutes}м азимут {a}°: T_in status={st_in}"); continue
            log_probe(sid, f"out-{minutes}", out_t)
            log_probe(sid, f"in-{minutes}", in_t)
            err = abs(in_t - out_t) / out_t
            rows.append({"school": sid, "school_name": name, "min": minutes, "azimuth": a,
                         "dist_km": round(km(spt, p), 2), "T_out": out_t, "T_in": in_t,
                         "err": round(err, 4), "T_in_over_threshold": int(in_t > minutes * 60)})
            print(f"  {minutes}м азимут {a:3}°: T_out={out_t}с T_in={in_t}с err={err:.1%} d={km(spt,p):.2f}км")

out_csv = ROOT / "data" / "out" / "stage4_direction_error.csv"
with open(out_csv, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)

print("\n=== МЕТРИКИ ===")
for sid in IDS:
    for m in (20, 40):
        sub = [r for r in rows if r["school"] == sid and r["min"] == m]
        if not sub:
            continue
        errs = sorted(r["err"] for r in sub)
        over = sum(r["T_in_over_threshold"] for r in sub)
        print(f"{sid[:30]:32} {m:2}м: медиана {errs[len(errs)//2]:.1%}, макс {errs[-1]:.1%}, "
              f"T_in>порога {over}/{len(sub)}")
all_errs = sorted(r["err"] for r in rows)
over_all = sum(r["T_in_over_threshold"] for r in rows)
print(f"ВСЕГО (n={len(rows)}): медиана {all_errs[len(all_errs)//2]:.1%}, макс {all_errs[-1]:.1%}, "
      f"T_in>порога {over_all}/{len(rows)}")
print("CSV:", out_csv)

# гистограмма
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
fig, axes = plt.subplots(1, 3, figsize=(14, 4.2), sharey=True)
for ax, sid in zip(axes, IDS):
    sub = [r["err"] for r in rows if r["school"] == sid]
    ax.hist([x * 100 for x in sub], bins=12, color="#4477aa")
    ax.set_title(schools[sid][0][:30], fontsize=9)
    ax.set_xlabel("|T_in−T_out|/T_out, %")
axes[0].set_ylabel("точек")
fig.suptitle("Стадия 4: ошибка направления ОТ (от школы vs к школе)", fontsize=11)
fig.tight_layout()
png = ROOT / "reports" / "plots" / "stage4_hist.png"
fig.savefig(png, dpi=110)
print("гистограмма:", png)
