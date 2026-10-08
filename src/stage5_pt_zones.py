"""Стадия 5 (ОТ): зоны 20/40 мин «от школы» для всех 20 школ — один изохронный запрос на школу.

Метод (гейты 3/4): reverse для ОТ не работает → зона «от школы» (приближение «к школе»,
ошибка оценивается в Стадии 4). start_time = DATE 05:30Z (8:30 МСК), все виды транспорта,
durations [1200, 2400] одним запросом. При 429/лимите — стоп без повторов (клиент).
"""
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import yaml
from shapely import wkt as shapely_wkt
from shapely import to_geojson
from client import isochrone, msk_to_utc, QuotaExhaustedError

ROOT = Path(__file__).resolve().parent.parent
CFG = yaml.safe_load((ROOT / "config" / "experiment.yaml").read_text(encoding="utf-8"))
DATE = CFG["date"]

schools = []
with open(ROOT / "config" / "schools.csv", encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        if r["selected"] == "1":
            schools.append((r["entity_id"], r["name"], float(r["lat"]), float(r["lon"])))

features = []
done, cache_hits, errors = 0, 0, 0
try:
    for sid, name, lat, lon in schools:
        r = isochrone(lat=lat, lon=lon, durations=[1200, 2400], transport="public_transport",
                      start_time=msk_to_utc(DATE, "08:30"))
        if r["status"] != 200 or not isinstance(r["data"], dict):
            errors += 1
            print(f"{sid[:30]}: статус {r['status']} — пропуск")
            continue
        geoms = [shapely_wkt.loads(i["geometry"]) for i in r["data"].get("isochrones", [])]
        if len(geoms) != 2:
            print(f"{sid[:30]}: ожидали 2 полигона, получено {len(geoms)}")
            errors += 1
            continue
        geoms.sort(key=lambda g: g.area)  # меньшая = 20 мин
        if r.get("cached"):
            cache_hits += 1
        for g, minutes in zip(geoms, (20, 40)):
            valid = g.is_valid
            if not valid:
                g = g.buffer(0)
            features.append({
                "type": "Feature",
                "properties": {
                    "school_id": sid, "name": name, "min": minutes, "mode": "public_transport",
                    "method": "isochrone pt reverse:false",
                    "status": "approx: зона «от школы»; ошибка направления — Стадия 4",
                    "start_time": msk_to_utc(DATE, "08:30"),
                    "request_hash": r.get("request_hash"),
                    "was_invalid": not valid,
                },
                "geometry": json.loads(to_geojson(g)),
            })
        done += 1
        print(f"{done:2}/20 {sid[:36]:38} ok{' (кэш)' if r.get('cached') else ''}")
except QuotaExhaustedError as e:
    print("СТОП по лимиту:", e)

out = ROOT / "data" / "out" / "pt_zones.geojson"
out.write_text(json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False), encoding="utf-8")
print(f"\nшкол обработано: {done}/20 (из кэша {cache_hits}), ошибок {errors}, полигонов {len(features)}")
print("сохранено:", out)
