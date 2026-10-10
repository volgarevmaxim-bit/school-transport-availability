"""Зоны ОТ 20/40 от трёх адресов владельца (09.10) → data/out/address_zones_pt.geojson.

3 изохронных запроса (durations=[1200,2400] одним, start 05:30Z) — ровно остаток
сегодняшнего лимита isochrone (42/50 сделано, резерв 5). Авто-зоны адресов — завтра
(6 запросов, свежий счётчик). Мерж идемпотентен по (address_id, min).
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
OUT = ROOT / "data" / "out" / "address_zones_pt.geojson"

addrs = []
with open(ROOT / "config" / "addresses.csv", encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        addrs.append((r["id"], r["label"], r["name"], float(r["lat"]), float(r["lon"])))

start = msk_to_utc(DATE, "08:30")
features, done, errors = [], 0, 0
try:
    for aid, label, name, lat, lon in addrs:
        r = isochrone(lat=lat, lon=lon, durations=[1200, 2400],
                      transport="public_transport", start_time=start)
        if r["status"] != 200 or not isinstance(r["data"], dict):
            errors += 1
            print(f"{label}: статус {r['status']} — пропуск")
            continue
        iso = sorted(r["data"].get("isochrones", []), key=lambda i: i.get("duration", 10**9))
        if len(iso) != 2:
            errors += 1
            print(f"{label}: ожидали 2 полигона, получено {len(iso)} — пропуск")
            continue
        for i in iso:
            minutes = i["duration"] // 60
            g = shapely_wkt.loads(i["geometry"])
            valid = g.is_valid
            if not valid:
                g = g.buffer(0)
            features.append({
                "type": "Feature",
                "properties": {
                    "address_id": aid, "label": label, "name": name, "min": minutes,
                    "mode": "public_transport",
                    "method": "isochrone pt reverse:false",
                    "status": "approx: зона «от адреса» (для ОТ reverse игнорируется)",
                    "start_time": start, "request_hash": r.get("request_hash"),
                    "was_invalid": not valid,
                },
                "geometry": json.loads(to_geojson(g)),
            })
        done += 1
        print(f"{done}/3 {label:12} ok{' (кэш)' if r.get('cached') else ''}")
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

print(f"\nадресов с зонами: {done}/3, ошибок {errors}, полигонов {len(zones['features'])}")
print("сохранено:", OUT)
