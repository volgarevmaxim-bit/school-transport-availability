"""Стадия 4 (дополнение): T_out-контроль — обратное направление (школа→точка), старт 8:30.

Выборка: 10 точек из stage4_tin.csv, где T_in (точка→школа) ПРЕВЫСИЛ порог 40-мин зоны
(Л2Ш 4/5, 1532 3/5, 2007 3/5 — по итогам 09.10). Те же граничные точки пересчитываются
детерминированно: пересечение луча азимута с границей 40-мин зоны из pt_zones.geojson
(0 изохронных запросов). T_out: школа→точка, выезд 8:30 МСК (метро принят → включаем).

Метрики: T_out vs порог 2400с; дельта T_out − T_in (асимметрия направлений);
принадлежность точки 40-мин зоне. QuotaExhaustedError → частичный CSV сохраняется.
"""
import csv
import json
import math
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import yaml
from shapely import from_geojson
from shapely.geometry import LineString, Point
from client import public_transport_route, msk_to_unix, QuotaExhaustedError

ROOT = Path(__file__).resolve().parent.parent
CFG = yaml.safe_load((ROOT / "config" / "experiment.yaml").read_text(encoding="utf-8"))
DATE = CFG["date"]
DB = ROOT / "data" / "db" / "experiments.sqlite"

TRANSPORTS = ["metro", "bus", "trolleybus", "tram"]   # metro принят pt/2.0 (09.10, все 200)
OUT_START = "08:30"
OUT_UNIX = msk_to_unix(DATE, OUT_START)
MINUTES = 40
THRESHOLD = MINUTES * 60

ZONES = json.loads((ROOT / "data" / "out" / "pt_zones.geojson").read_text(encoding="utf-8"))

schools = {}
with open(ROOT / "config" / "schools.csv", encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        if r["selected"] == "1":
            schools[r["entity_id"]] = (r["name"], float(r["lat"]), float(r["lon"]))

# точки: из stage4_tin.csv — все с T_in>порога в 40-мин зонах
tin = list(csv.DictReader(open(ROOT / "data" / "out" / "stage4_tin.csv", encoding="utf-8-sig")))
sel = [r for r in tin if int(r["min"]) == MINUTES and r["T_in_over_threshold"] == "1"]
print(f"точек с T_in>порога в 40-мин зонах: {len(sel)}")


def zone_poly(sid, minutes):
    for f in ZONES["features"]:
        p = f["properties"]
        if p["school_id"] == sid and p["min"] == minutes:
            return from_geojson(json.dumps(f["geometry"]))
    return None


def boundary_point(poly, spt, azimuth_deg, r_deg=0.6):
    rad = math.radians(azimuth_deg)
    end = Point(spt.x + r_deg * math.cos(rad), spt.y + r_deg * math.sin(rad))
    inter = poly.boundary.intersection(LineString([spt, end]))
    if inter.is_empty:
        return None
    pts = [inter] if isinstance(inter, Point) else [g for g in inter.geoms]
    return min(pts, key=lambda p: spt.distance(p))


def km(spt, p):
    return spt.distance(p) * 111.32 * math.cos(math.radians(spt.y))


def log_probe(school, hyp, t):
    con = sqlite3.connect(DB)
    con.execute("INSERT INTO probes(school_id, mode, hypothesis, t_sec, method_version) VALUES(?,?,?,?,?)",
                (school, "pt", hyp, t, "v1"))
    con.commit()
    con.close()


def pt_duration(lonlat_a, lonlat_b, start_unix, transports):
    r = public_transport_route(lonlat_a, lonlat_b, start_time_unix=start_unix,
                               enable_schedule=True, transports=transports)
    if r["status"] != 200:
        return None, r["status"], None
    data = r["data"]
    if isinstance(data, dict):
        return None, f"200-dict: {str(data)[:120]}", None
    if not isinstance(data, list) or not data:
        return None, "200-empty", None
    return data[0]["total_duration"], 200, r.get("request_hash")


rows, n_queries = [], 0
try:
    for r in sel:
        sid = r["school"]
        name, lat, lon = schools[sid]
        spt = Point(lon, lat)
        az = int(r["azimuth"])
        poly = zone_poly(sid, MINUTES)
        p = boundary_point(poly, spt, az)
        if p is None:
            print(f"{name[:30]} аз{az:3}°: граница не найдена — пропуск")
            continue
        pll = f"{p.x:.6f},{p.y:.6f}"
        t, st, h = pt_duration(f"{lon},{lat}", pll, OUT_UNIX, TRANSPORTS)
        n_queries += 1
        if t is None:
            print(f"{name[:30]} аз{az:3}°: status={st}")
            continue
        log_probe(sid, f"out-{MINUTES}", t)
        tin_sec = int(r["T_in"])
        inside = poly.intersects(p) or poly.boundary.intersects(p)
        over = int(t > THRESHOLD)
        rows.append({"school": sid, "school_name": name, "min": MINUTES, "azimuth": az,
                     "dist_km": round(km(spt, p), 2), "T_in": tin_sec, "T_out": t,
                     "threshold": THRESHOLD, "T_out_over_threshold": over,
                     "T_out_minus_T_in": t - tin_sec, "on_zone_boundary": int(inside)})
        print(f"{name[:30]} аз{az:3}°: T_out={t}с порог={THRESHOLD}с "
              f"{'>ПОРОГА' if over else 'ok'} (T_in={tin_sec}с, Δ={t - tin_sec:+}с) d={km(spt, p):.2f}км")
except QuotaExhaustedError as e:
    print("СТОП по лимиту (429):", e)

out_csv = ROOT / "data" / "out" / "stage4_tout.csv"
if rows:
    with open(out_csv, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"\nCSV (частичный при остановке): {out_csv}")
else:
    print("\nCSV не записан: нет строк")

print("\n=== МЕТРИКИ T_out (школа→точка, выезд 8:30) ===")
for sid in sorted({r["school"] for r in rows}):
    sub = [r for r in rows if r["school"] == sid]
    ts = sorted(r["T_out"] for r in sub)
    over = sum(r["T_out_over_threshold"] for r in sub)
    print(f"{sid[:30]:32} 40м (n={len(sub)}): медиана {ts[len(ts)//2]}с, макс {ts[-1]}с, "
          f"T_out>порога {over}/{len(sub)}")
if rows:
    ts = sorted(r["T_out"] for r in rows)
    over_all = sum(r["T_out_over_threshold"] for r in rows)
    deltas = sorted(r["T_out_minus_T_in"] for r in rows)
    print(f"ВСЕГО (n={len(rows)}): медиана {ts[len(ts)//2]}с, T_out>порога {over_all}/{len(rows)}")
    print(f"асимметрия T_out−T_in: медиана {deltas[len(deltas)//2]:+}с, мин {deltas[0]:+}с, макс {deltas[-1]:+}с")
print("pt-запросов сделано:", n_queries)
