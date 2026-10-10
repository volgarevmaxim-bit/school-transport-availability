"""АВТО-зоны 20/40 от трёх адресов владельца → data/out/address_zones_car.geojson.

6 изохронных запросов (3 адреса × 20/40, driving reverse:true). Гипотеза A (Гейт 2):
start_time = время ВЫЕЗДА = 8:30 МСК − минуты → 20→05:10Z, 40→04:50Z; каждый старт —
отдельный запрос. Мерж идемпотентен по (address_id, min). QuotaExhaustedError →
сохраняем собранное частично.
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
OUT = ROOT / "data" / "out" / "address_zones_car.geojson"

addrs = []
with open(ROOT / "config" / "addresses.csv", encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        addrs.append((r["id"], r["label"], r["name"], float(r["lat"]), float(r["lon"])))

jobs = [(aid, label, name, lat, lon, m) for aid, label, name, lat, lon in addrs for m in (20, 40)]

features, done, errors = [], 0, 0
try:
    for aid, label, name, lat, lon, minutes in jobs:
        dep_min = 8 * 60 + 30 - minutes   # выезд = 8:30 МСК − минуты
        h, mm = divmod(dep_min, 60)
        start = msk_to_utc(DATE, f"{h:02d}:{mm:02d}")
        r = isochrone(lat=lat, lon=lon, durations=[minutes * 60], transport="driving",
                      reverse=True, start_time=start)
        if r["status"] != 200 or not isinstance(r["data"], dict):
            errors += 1
            print(f"{label}: {minutes}м статус {r['status']} — пропуск")
            continue
        iso = r["data"].get("isochrones", [])
        if len(iso) != 1:
            errors += 1
            print(f"{label}: {minutes}м ожидали 1 полигон, получено {len(iso)} — пропуск")
            continue
        g = shapely_wkt.loads(iso[0]["geometry"])
        valid = g.is_valid
        if not valid:
            g = g.buffer(0)
        features.append({
            "type": "Feature",
            "properties": {
                "address_id": aid, "label": label, "name": name, "min": minutes,
                "mode": "driving",
                "method": "isochrone driving reverse:true",
                "status": "approx: гипотеза A (start_time = выезд), +8–14% (Гейт 2)",
                "start_time": start, "request_hash": r.get("request_hash"),
                "was_invalid": not valid,
            },
            "geometry": json.loads(to_geojson(g)),
        })
        done += 1
        print(f"{done}/{len(jobs)} {label:12} {minutes:2}м ok{' (кэш)' if r.get('cached') else ''}")
except QuotaExhaustedError as e:
    print("СТОП по лимиту:", e)

if OUT.exists():
    zones = json.loads(OUT.read_text(encoding="utf-8"))
    keys_new = {(f["properties"]["address_id"], f["properties"]["min"]) for f in features}
    kept = [f for f in zones["features"]
            if (f["properties"]["address_id"], f["properties"]["min"]) not in keys_new]
    zones["features"] = kept + features
else:
    zones = {"type": "FeatureCollection", "features": features}
OUT.write_text(json.dumps(zones, ensure_ascii=False), encoding="utf-8")

print(f"\nадресов с зонами: {done}/{len(addrs)}, ошибок {errors}, полигонов {len(zones['features'])}")
print("сохранено:", OUT)
