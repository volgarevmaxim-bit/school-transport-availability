# -*- coding: utf-8 -*-
"""Гимназия №1543: ОТ-зоны 25/30/35 мин (решение владельца 10.10).

Один изохронный запрос public_transport с durations [1500, 1800, 2100],
start_time = DATE 05:30Z (8:30 МСК). Идемпотентный мерж в data/out/pt_zones.geojson:
заменяются ТОЛЬКО фичи (school_id=1543, min in {25,30,35}); зоны 20/40 у 1543
и все зоны других школ не трогаются.
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
OUT = ROOT / "data" / "out" / "pt_zones.geojson"

with open(ROOT / "config" / "schools.csv", encoding="utf-8-sig") as f:
    row = next(r for r in csv.DictReader(f) if r["entity_id"] == SID)
name, lat, lon = row["name"], float(row["lat"]), float(row["lon"])

features = []
r = isochrone(lat=lat, lon=lon, durations=[1500, 1800, 2100],
              transport="public_transport", start_time=msk_to_utc(DATE, "08:30"))
if r["status"] != 200 or not isinstance(r["data"], dict):
    print("ОШИБКА:", r["status"]); sys.exit(1)
iso = r["data"].get("isochrones", [])
if len(iso) != 3:
    print("ожидали 3 полигона, получено", len(iso)); sys.exit(1)
geoms = [shapely_wkt.loads(i["geometry"]) for i in iso]
geoms.sort(key=lambda g: g.area)  # меньшая = 25 мин
for g, minutes in zip(geoms, (25, 30, 35)):
    valid = g.is_valid
    if not valid:
        g = g.buffer(0)
    features.append({
        "type": "Feature",
        "properties": {
            "school_id": SID, "name": name, "min": minutes, "mode": "public_transport",
            "method": "isochrone pt reverse:false (25/30/35, решение владельца 10.10)",
            "status": "approx: зона «от школы»; ошибка направления — Стадия 4",
            "start_time": msk_to_utc(DATE, "08:30"),
            "request_hash": r.get("request_hash"),
            "was_invalid": not valid,
        },
        "geometry": json.loads(to_geojson(g)),
    })

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
print(f"1543 pt-зоны: {dict(sorted(by_min.items()))} | всего полигонов в файле: {len(zones['features'])}")
