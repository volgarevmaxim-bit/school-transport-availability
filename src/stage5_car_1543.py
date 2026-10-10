# -*- coding: utf-8 -*-
"""Гимназия №1543: авто-зоны 25/30/35 мин (решение владельца 10.10).

Как в stage5_car_zones.py (Л2Ш 25/30/35): три запроса driving reverse:true,
start_time = время выезда = 8:30 МСК − minutes (25→05:05Z, 30→05:00Z, 35→04:55Z).
Идемпотентный мерж в data/out/car_zones.geojson: заменяются ТОЛЬКО фичи
(school_id=1543, min in {25,30,35}).
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
SID = "московская-гимназия-на-юго-западе-1543-ю-в-завельского"
OUT = ROOT / "data" / "out" / "car_zones.geojson"

with open(ROOT / "config" / "schools.csv", encoding="utf-8-sig") as f:
    row = next(r for r in csv.DictReader(f) if r["entity_id"] == SID)
name, lat, lon = row["name"], float(row["lat"]), float(row["lon"])

features, errors = [], 0
try:
    for minutes in (25, 30, 35):
        dep_min = 8 * 60 + 30 - minutes
        h, mm = divmod(dep_min, 60)
        start = msk_to_utc(DATE, f"{h:02d}:{mm:02d}")
        r = isochrone(lat=lat, lon=lon, durations=[minutes * 60], transport="driving",
                      reverse=True, start_time=start)
        if r["status"] != 200 or not isinstance(r["data"], dict):
            errors += 1
            print(f"{minutes}м: статус {r['status']} — пропуск")
            continue
        iso = r["data"].get("isochrones", [])
        if len(iso) != 1:
            errors += 1
            print(f"{minutes}м: ожидали 1 полигон, получено {len(iso)} — пропуск")
            continue
        g = shapely_wkt.loads(iso[0]["geometry"])
        valid = g.is_valid
        if not valid:
            g = g.buffer(0)
        features.append({
            "type": "Feature",
            "properties": {
                "school_id": SID, "name": name, "min": minutes, "mode": "driving",
                "method": "isochrone driving reverse:true (25/30/35, решение владельца 10.10)",
                "status": "approx: гипотеза A (start_time = выезд), +8–14% (Гейт 2)",
                "start_time": start, "request_hash": r.get("request_hash"),
                "was_invalid": not valid,
            },
            "geometry": json.loads(to_geojson(g)),
        })
        print(f"{minutes:2}м ok{' (кэш)' if r.get('cached') else ''}")
except QuotaExhaustedError as e:
    print("СТОП по лимиту:", e)

zones = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {"type": "FeatureCollection", "features": []}
kept = [f for f in zones["features"]
        if not (f["properties"]["school_id"] == SID and f["properties"]["min"] in (25, 30, 35))]
zones["features"] = kept + features
OUT.write_text(json.dumps(zones, ensure_ascii=False), encoding="utf-8")

by_min = {}
for f in zones["features"]:
    p = f["properties"]
    if p["school_id"] == SID:
        by_min.setdefault(p["min"], 0)
        by_min[p["min"]] += 1
print(f"1543 авто-зоны: {dict(sorted(by_min.items()))} | всего полигонов: {len(zones['features'])} | ошибок: {errors}")
