"""Стадия 5 (авто): зоны «к школе» (driving reverse:true) — 20 школ × 20/40 мин + Л2Ш 25/30/35.

Гипотеза A (Гейт 2): start_time = время ВЫЕЗДА = 8:30 МСК − minutes → 20→05:10Z, 40→04:50Z,
25→05:05Z, 30→05:00Z, 35→04:55Z. Каждый старт — отдельный запрос (один start_time на запрос).
reverse:true для driving работает и чувствителен к start_time (Гейт 2).

ОЧЕРЕДЬ (решение владельца 09.10): сначала Л2Ш 25/30/35 (приоритет), затем все школы 20/40.
Итого 3 + 40 = 43 запроса изохрон (лимит 45 с резервом). Мерж в car_zones.geojson
идемпотентен (school_id+min → замена). При QuotaExhaustedError — сохраняем, что успели.
"""
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import yaml
from shapely import wkt as shapely_wkt, to_geojson
from client import isochrone, msk_to_utc, QuotaExhaustedError

ROOT = Path(__file__).resolve().parent.parent
CFG = yaml.safe_load((ROOT / "config" / "experiment.yaml").read_text(encoding="utf-8"))
DATE = CFG["date"]
L2SH = "лицей-вторая-школа-в-ф-овчинникова"
OUT = ROOT / "data" / "out" / "car_zones.geojson"

schools = []
with open(ROOT / "config" / "schools.csv", encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        if r["selected"] == "1":
            schools.append((r["entity_id"], r["name"], float(r["lat"]), float(r["lon"])))

jobs = []  # (sid, name, lat, lon, minutes)
l2 = next(s for s in schools if s[0] == L2SH)
for m in (25, 30, 35):            # приоритет владельца — первыми
    jobs.append((*l2, m))
for s in schools:
    for m in (20, 40):
        jobs.append((*s, m))

features, done, cache_hits, errors = [], 0, 0, 0
try:
    for sid, name, lat, lon, minutes in jobs:
        dep_min = 8 * 60 + 30 - minutes   # выезд = 8:30 МСК − минуты
        h, mm = divmod(dep_min, 60)
        start = msk_to_utc(DATE, f"{h:02d}:{mm:02d}")
        r = isochrone(lat=lat, lon=lon, durations=[minutes * 60], transport="driving",
                      reverse=True, start_time=start)
        if r["status"] != 200 or not isinstance(r["data"], dict):
            errors += 1
            print(f"{sid[:30]}: {minutes}м статус {r['status']} — пропуск")
            continue
        iso = r["data"].get("isochrones", [])
        if len(iso) != 1:
            errors += 1
            print(f"{sid[:30]}: {minutes}м ожидали 1 полигон, получено {len(iso)} — пропуск")
            continue
        g = shapely_wkt.loads(iso[0]["geometry"])
        valid = g.is_valid
        if not valid:
            g = g.buffer(0)
        features.append({
            "type": "Feature",
            "properties": {
                "school_id": sid, "name": name, "min": minutes, "mode": "driving",
                "method": "isochrone driving reverse:true",
                "status": "approx: гипотеза A (start_time = выезд), +8–14% (Гейт 2)",
                "start_time": start, "request_hash": r.get("request_hash"),
                "was_invalid": not valid,
            },
            "geometry": json.loads(to_geojson(g)),
        })
        done += 1
        if r.get("cached"):
            cache_hits += 1
        print(f"{done:2}/{len(jobs)} {sid[:36]:38} {minutes:2}м{' (кэш)' if r.get('cached') else ''}")
except QuotaExhaustedError as e:
    print("СТОП по лимиту:", e)

# идемпотентный мерж: заменяем фичи по (school_id, min), сохраняя порядок остальных
if OUT.exists():
    zones = json.loads(OUT.read_text(encoding="utf-8"))
    keys_new = {(f["properties"]["school_id"], f["properties"]["min"]) for f in features}
    kept = [f for f in zones["features"]
            if (f["properties"]["school_id"], f["properties"]["min"]) not in keys_new]
    zones["features"] = kept + features
else:
    zones = {"type": "FeatureCollection", "features": features}
OUT.write_text(json.dumps(zones, ensure_ascii=False), encoding="utf-8")

print(f"\nзапросов ok: {done}/{len(jobs)} (из кэша {cache_hits}), ошибок {errors}")
print(f"car_zones.geojson: {len(zones['features'])} полигонов")
by_min = {}
for f in zones["features"]:
    by_min.setdefault(f["properties"]["min"], 0)
    by_min[f["properties"]["min"]] += 1
print("по минутам:", dict(sorted(by_min.items())))
