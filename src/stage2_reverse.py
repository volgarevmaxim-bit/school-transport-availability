"""Стадия 2: семантика start_time для reverse:true (driving).

Вопрос: start_time при reverse:true — выезд с границы (гипотеза A: маршрут стартует в 05:10Z)
или прибытие к школе (гипотеза B: выезд = start_time − 1200 с = 04:50Z).

1. P_rev = isochrone driving 1200 с, reverse true, 05:10Z.
2. P_fwd = то же, reverse false (контроль: площадь/форма должны заметно различаться).
3. 12 точек на границе P_rev (равномерно по длине контура) → маршрут точка→школа на 05:10Z (A)
   и 04:50Z (B) через routing/7.0.0 (statistics).
4. Метрики: медиана и макс |t−1200|/1200 для A и B; принятие при медиане ≤ 10%.
5. Повтор на второй школе (центр vs периферия).
"""
import csv
import math
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import yaml
from shapely.geometry import LineString, MultiLineString, Point
from shapely import wkt as shapely_wkt
from client import isochrone, directions_driving, msk_to_utc, msk_to_unix

ROOT = Path(__file__).resolve().parent.parent
CFG = yaml.safe_load((ROOT / "config" / "experiment.yaml").read_text(encoding="utf-8"))
DATE = CFG["date"]
DB = ROOT / "data" / "db" / "experiments.sqlite"

schools = {}
with open(ROOT / "config" / "schools.csv", encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        if r["selected"] == "1":
            schools[r["entity_id"]] = (r["name"], float(r["lat"]), float(r["lon"]))

S1 = "лицей-вторая-школа-в-ф-овчинникова"   # ближе к центру
S2 = "школа-2007-фмш"                        # периферия, Ю.Бутово
N_POINTS = 12
TARGET = 1200


def log_probe(school, hypothesis, t):
    con = sqlite3.connect(DB)
    con.execute("INSERT INTO probes(school_id, mode, hypothesis, t_sec, method_version) VALUES(?,?,?,?,?)",
                (school, "driving", hypothesis, t, "v1"))
    con.commit()
    con.close()


def log_verdict(gate, result, note):
    con = sqlite3.connect(DB)
    con.execute("INSERT INTO verdicts(gate, result, note, utc_time) VALUES(?,?,?,datetime('now'))",
                (gate, result, note))
    con.commit()
    con.close()


def iso_driving(sid, reverse, start_utc):
    name, lat, lon = schools[sid]
    r = isochrone(lat=lat, lon=lon, durations=[TARGET], transport="driving",
                  reverse=reverse, start_time=start_utc)
    if r["status"] != 200 or not isinstance(r["data"], dict):
        raise RuntimeError(f"{sid} isochrone status={r['status']}: {str(r['data'])[:200]}")
    iso = r["data"].get("isochrones") or []
    if not iso:
        raise RuntimeError(f"{sid}: isochrones пуст")
    return shapely_wkt.loads(iso[0]["geometry"]), r["request_hash"]


def area_km2(g):
    lat = g.centroid.y
    return g.area * 111.32 * 111.32 * math.cos(math.radians(lat))


def sample_boundary(g, n):
    """n точек на границе, равномерно по длине контура."""
    lines = list(g.boundary.geoms) if isinstance(g.boundary, MultiLineString) else [g.boundary]
    samples = []
    total = 0.0
    for l in lines:
        coords = list(l.coords)
        for i in range(len(coords) - 1):
            samples.append((total, Point(coords[i])))
            total += LineString([coords[i], coords[i + 1]]).length
        samples.append((total, Point(coords[-1])))
    return [min(samples, key=lambda s: abs(s[0] - k * total / n))[1] for k in range(n)]


def probe_school(sid):
    name, lat, lon = schools[sid]
    print(f"\n=== {name} ({sid[:30]}) ===")
    p_rev, h_rev = iso_driving(sid, True, msk_to_utc(DATE, "08:10"))
    p_fwd, h_fwd = iso_driving(sid, False, msk_to_utc(DATE, "08:10"))
    print(f"P_rev: площадь {area_km2(p_rev):.1f} км² (hash {h_rev[:10]})")
    print(f"P_fwd: площадь {area_km2(p_fwd):.1f} км² (hash {h_fwd[:10]})")
    print(f"площадь rev/fwd = {area_km2(p_rev)/area_km2(p_fwd):.2f}, IoU = {p_rev.intersection(p_fwd).area/max(p_rev.union(p_fwd).area,1e-12):.2f}")

    pts = sample_boundary(p_rev, N_POINTS)
    errs = {"A": [], "B": []}
    for i, p in enumerate(pts):
        pll = f"{p.x:.6f},{p.y:.6f}"
        tA = directions_driving(pll, f"{lon},{lat}", utc_unix=msk_to_unix(DATE, "08:10"))
        tB = directions_driving(pll, f"{lon},{lat}", utc_unix=msk_to_unix(DATE, "07:50"))
        for hyp, r in (("A", tA), ("B", tB)):
            if r["status"] == 200 and isinstance(r["data"], dict) and r["data"].get("result"):
                t = r["data"]["result"][0]["duration"]
                log_probe(sid, hyp, t)
                errs[hyp].append(abs(t - TARGET) / TARGET)
            else:
                print(f"  точка {i}: гипотеза {hyp} status={r['status']} — пропуск")
        print(f"  точка {i:2}: tA={tA['data']['result'][0]['duration'] if tA['status']==200 and tA['data'].get('result') else '-'}с  "
              f"tB={tB['data']['result'][0]['duration'] if tB['status']==200 and tB['data'].get('result') else '-'}с")
    print("гипотеза A (старт 05:10Z): медианная ошибка {:.1%}, макс {:.1%} (n={})".format(
        sorted(errs['A'])[len(errs['A'])//2] if errs['A'] else float('nan'),
        max(errs['A']) if errs['A'] else float('nan'), len(errs['A'])))
    print("гипотеза B (старт 04:50Z): медианная ошибка {:.1%}, макс {:.1%} (n={})".format(
        sorted(errs['B'])[len(errs['B'])//2] if errs['B'] else float('nan'),
        max(errs['B']) if errs['B'] else float('nan'), len(errs['B'])))
    return p_rev, p_fwd, pts, errs


def main():
    results = {}
    for sid in (S1, S2):
        results[sid] = probe_school(sid)

    verdicts = {}
    for sid, (p_rev, p_fwd, pts, errs) in results.items():
        medA = sorted(errs["A"])[len(errs["A"]) // 2] if errs["A"] else float("inf")
        medB = sorted(errs["B"])[len(errs["B"]) // 2] if errs["B"] else float("inf")
        verdicts[sid] = "A" if medA <= 0.10 else ("B" if medB <= 0.10 else "ни одна")
    print("\n=== ВЕРДИКТ СТАДИИ 2 ===")
    print("S1 (Л2Ш):", verdicts[S1])
    print("S2 (2007 ФМШ):", verdicts[S2])
    log_verdict("ГЕЙТ 2", " | ".join(f"{k}:{v}" for k, v in verdicts.items()), "метрика: медиана ≤10%")


if __name__ == "__main__":
    main()
