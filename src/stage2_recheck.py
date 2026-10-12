"""Стадия 2 (перепроверка 12.10): семантика start_time для reverse:true (driving), чистый прогон.

Прогон 08.10 имел дефекты: 8×429 в серии, выборка границы по вершинам дала артефакт
(точка у школы 2007-фмш, t=335с, ошибка 72%). Здесь:
- P_rev/P_fwd из кэша 08.10 (изохроны DATE 14.10, 1200с, 05:10Z) — 0 новых изохрон;
- 10 точек на границе P_rev азимутальными лучами (каждые 36°, самая дальняя точка
  пересечения луча с границей; метрика — метры на широте школы);
- гипотеза A: маршрут точка→школа стартует 05:10Z (start_time = выезд с границы);
- гипотеза B: старт 04:50Z (start_time = прибытие, выезд на 20 мин раньше);
- метрики: медиана/макс |t−1200|/1200; порог принятия — медиана ≤ 10% (ТЗ).
- БЕЗ повторов (429 → QuotaExhaustedError → частичный CSV сохраняется).
"""
import csv
import json
import math
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import yaml
from shapely.geometry import LineString, MultiPoint, Point, shape
from shapely import wkt as shapely_wkt
from client import (
    QuotaExhaustedError, directions_driving, isochrone, msk_to_unix, msk_to_utc,
)

ROOT = Path(__file__).resolve().parent.parent
CFG = yaml.safe_load((ROOT / "config" / "experiment.yaml").read_text(encoding="utf-8"))
DATE = CFG["date"]
DB = ROOT / "data" / "db" / "experiments.sqlite"
OUT_CSV = ROOT / "data" / "out" / "stage2_recheck.csv"
OUT_GEOJSON = ROOT / "data" / "out" / "stage2_recheck_points.geojson"

S1 = "лицей-вторая-школа-в-ф-овчинникова"   # центр
S2 = "школа-2007-фмш"                        # периферия, Ю.Бутово
N_AZIMUTH = 10
TARGET = 1200
M_PER_DEG_LAT = 111320.0

schools = {}
with open(ROOT / "config" / "schools.csv", encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        if r["selected"] == "1":
            schools[r["entity_id"]] = (r["name"], float(r["lat"]), float(r["lon"]))


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
    """Изохрона из кэша (0 новых) или вживую, если кэша нет."""
    name, lat, lon = schools[sid]
    r = isochrone(lat=lat, lon=lon, durations=[TARGET], transport="driving",
                  reverse=reverse, start_time=start_utc)
    src = "cache" if r.get("cached") else "LIVE"
    if r["status"] != 200 or not isinstance(r["data"], dict):
        raise RuntimeError(f"{sid} isochrone status={r['status']}: {str(r['data'])[:200]}")
    iso = r["data"].get("isochrones") or []
    if not iso:
        raise RuntimeError(f"{sid}: isochrones пуст")
    print(f"  {sid[:28]:30s} rev={reverse} {src} (hash {r.get('request_hash','?')[:10]})")
    return shapely_wkt.loads(iso[0]["geometry"])


def sample_azimuthal(poly, lat0, lon0, n=N_AZIMUTH):
    """n точек: лучи из школы каждые 360/n° (0 = север), самая дальняя точка пересечения
    с границей полигона. Метрика — локальные метры (м/град с поправкой cos(lat))."""
    m_per_deg_lon = M_PER_DEG_LAT * math.cos(math.radians(lat0))

    def to_xy(pt):
        x, y = pt.x, pt.y
        return ((x - lon0) * m_per_deg_lon, (y - lat0) * M_PER_DEG_LAT)

    def to_ll(x, y):
        return Point(lon0 + x / m_per_deg_lon, lat0 + y / M_PER_DEG_LAT)

    # полигон в метровой метрике
    def ring_xy(coords):
        return [to_xy(Point(c[0], c[1])) for c in coords]

    polys = []
    for geom in (poly.geoms if poly.geom_type == "MultiPolygon" else [poly]):
        ext = ring_xy(list(geom.exterior.coords))
        holes = [ring_xy(list(h.coords)) for h in geom.interiors]
        polys.append((ext, holes))

    # радиус луча: макс. расстояние до границы + 1 км
    pts_xy = [p for ext, holes in polys for p in ext]
    rmax = max(math.hypot(x, y) for x, y in pts_xy) + 1000.0

    result = []
    for k in range(n):
        az = math.radians(k * 360.0 / n)
        dx, dy = rmax * math.sin(az), rmax * math.cos(az)  # 0° = север
        ray = LineString([(0.0, 0.0), (dx, dy)])
        best = None
        for ext, holes in polys:
            ext_ls = LineString(ext)
            cand = ext_ls.intersection(ray)
            if cand.is_empty:
                continue
            if cand.geom_type == "Point":
                cands = [cand]
            elif cand.geom_type == "MultiPoint":
                cands = list(cand.geoms)
            elif cand.geom_type == "GeometryCollection":
                cands = [g for g in cand.geoms if g.geom_type in ("Point",)]
            else:
                cands = []
            for c in cands:
                d = math.hypot(c.x, c.y)
                if best is None or d > best[0]:
                    best = (d, c)
        if best is None:
            raise RuntimeError(f"азимут {k * 36:.0f}°: нет пересечения луча с границей")
        result.append((k * 36.0, to_ll(best[1].x, best[1].y)))
    return result


def probe_point(pll, school_ll, utc_unix):
    return directions_driving(pll, school_ll, utc_unix=utc_unix)


def main():
    print(f"DATE={DATE}; гипотеза A: старт 05:10Z, B: старт 04:50Z; цель {TARGET}с")
    rows = []  # для CSV
    errs = {}
    tA_unix = msk_to_unix(DATE, "08:10")
    tB_unix = msk_to_unix(DATE, "07:50")

    # возобновляемость: уже измеренные (school, azimuth) из CSV не перезапрашиваем
    done = {}
    if OUT_CSV.exists():
        with open(OUT_CSV, encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                done[(r["school_id"], float(r["azimuth"]))] = r

    try:
        for sid in (S1, S2):
            name, lat, lon = schools[sid]
            errs[sid] = {"A": [], "B": []}
            # восстановить метрики из уже готовых строк
            for (dsid, _az), r in done.items():
                if dsid != sid:
                    continue
                for hyp in ("A", "B"):
                    if r.get(f"err{hyp}") not in (None, ""):
                        errs[sid][hyp].append(float(r[f"err{hyp}"]))
            print(f"\n=== {name} === (готово {sum(1 for k in done if k[0]==sid)}/10 азимутов)")
            p_rev = iso_driving(sid, True, msk_to_utc(DATE, "08:10"))
            p_fwd = iso_driving(sid, False, msk_to_utc(DATE, "08:10"))
            # отчёт площади rev vs fwd (контроль из ТЗ)
            def area_km2(g):
                return g.area * 111.32 * 111.32 * math.cos(math.radians(lat))
            print(f"  P_rev {area_km2(p_rev):.1f} км², P_fwd {area_km2(p_fwd):.1f} км², "
                  f"rev/fwd = {area_km2(p_rev)/area_km2(p_fwd):.2f}")

            pts = sample_azimuthal(p_rev, lat, lon)
            school_ll = f"{lon},{lat}"
            for az_deg, p in pts:
                if (sid, az_deg) in done:
                    rows.append(done[(sid, az_deg)])
                    continue
                pll = f"{p.x:.6f},{p.y:.6f}"
                row = {"school_id": sid, "azimuth": az_deg, "lon": p.x, "lat": p.y}
                for hyp, utc in (("A", tA_unix), ("B", tB_unix)):
                    r = probe_point(pll, school_ll, utc)
                    if r["status"] == 200 and isinstance(r["data"], dict) and r["data"].get("result"):
                        t = r["data"]["result"][0]["duration"]
                        log_probe(sid, hyp, t)
                        row[f"t{hyp}"] = t
                        row[f"err{hyp}"] = round(abs(t - TARGET) / TARGET, 4)
                        errs[sid][hyp].append(abs(t - TARGET) / TARGET)
                    else:
                        row[f"t{hyp}"] = None
                        row[f"err{hyp}"] = None
                        print(f"  азимут {az_deg:3.0f}° гипотеза {hyp}: status={r['status']} — пропуск")
                rows.append(row)
                print(f"  азимут {az_deg:3.0f}°: tA={row.get('tA')}с tB={row.get('tB')}с")
                time.sleep(0.6)  # сверх client-пейсинга 1.5с: ~2.1с между запросами
    except QuotaExhaustedError as e:
        print(f"\n!! {e}\nЧастичные результаты сохраняются (грабли 09.10).")

    # ---- метрики и вердикт ----
    print("\n=== МЕТРИКИ |t−1200|/1200 ===")
    verdicts = {}
    for sid in (S1, S2):
        name = schools[sid][0]
        for hyp in ("A", "B"):
            e = sorted(errs[sid][hyp])
            if e:
                med, mx = e[len(e) // 2], max(e)
                print(f"{name[:44]:46s} {hyp}: медиана {med:.1%}, макс {mx:.1%} (n={len(e)})")
        medA = sorted(errs[sid]["A"])[len(errs[sid]["A"]) // 2] if errs[sid]["A"] else float("inf")
        medB = sorted(errs[sid]["B"])[len(errs[sid]["B"]) // 2] if errs[sid]["B"] else float("inf")
        verdicts[sid] = "A" if medA <= 0.10 else ("B" if medB <= 0.10 else "ни одна")

    print("\n=== ВЕРДИКТ ===")
    for sid, v in verdicts.items():
        print(f"{schools[sid][0][:44]:46s} {v}")
    gate = "ГЕЙТ 2 (перепроверка 12.10)"
    res = " | ".join(f"{k}:{v}" for k, v in verdicts.items())
    con = sqlite3.connect(DB)
    n = con.execute("SELECT COUNT(*) FROM verdicts WHERE gate=?", (gate,)).fetchone()[0]
    if n:
        con.execute("UPDATE verdicts SET result=?, note=?, utc_time=datetime('now') WHERE gate=?",
                    (res, "азимутальная выборка 10°, медиана ≤10%", gate))
    else:
        con.execute("INSERT INTO verdicts(gate, result, note, utc_time) VALUES(?,?,?,datetime('now'))",
                    (gate, res, "азимутальная выборка 10°, медиана ≤10%"))
    con.commit()
    con.close()

    # ---- CSV + GeoJSON ----
    cols = ["school_id", "azimuth", "lon", "lat", "tA", "tB", "errA", "errB"]
    with open(OUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"\nCSV: {OUT_CSV} ({len(rows)} строк)")

    feats = [{"type": "Feature",
              "geometry": {"type": "Point", "coordinates": [r["lon"], r["lat"]]},
              "properties": {"school_id": r["school_id"], "azimuth": r["azimuth"],
                             "tA": r.get("tA"), "tB": r.get("tB")}}
             for r in rows if r.get("lon") is not None]
    OUT_GEOJSON.write_text(json.dumps({"type": "FeatureCollection", "features": feats},
                                      ensure_ascii=False), encoding="utf-8")
    print(f"GeoJSON: {OUT_GEOJSON}")


if __name__ == "__main__":
    main()
