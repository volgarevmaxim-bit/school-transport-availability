# -*- coding: utf-8 -*-
"""Точечный пересчёт зон ОДНОЙ школы (замена базового адреса) — 11.10, 3-я очередь.

При смене базового адреса школы (isochrone_base / schools.csv) её зоны в
pt_zones.geojson и car_zones.geojson устаревают. Полный прогон stage5_*_zones.py
пересчитал бы все 20 школ (43 car-запроса), поэтому здесь — только выбранная школа:

  pt: 1 изохронный запрос durations=[1200, 2400] (start 08:30 МСК, все виды ОТ) → 20/40
  car: 2 запроса driving reverse:true (20/40, start_time = выезд, гипотеза A)

Мерж идемпотентен по (school_id, min): старые фичи школы с этими min заменяются,
остальные (напр. Л2Ш 25/30/35) не трогаются. QuotaExhaustedError → сохраняем частично.

Запуск: python src/stage5_rezone_school.py <entity_id>
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

schools = {}
with open(ROOT / "config" / "schools.csv", encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        if r["selected"] == "1":
            schools[r["entity_id"]] = (r["name"], float(r["lat"]), float(r["lon"]))

if len(sys.argv) < 2 or sys.argv[1] not in schools:
    print("usage: stage5_rezone_school.py <entity_id>")
    sys.exit(1)

sid = sys.argv[1]
name, lat, lon = schools[sid]
print(f"пересчёт зон: {sid} | {name} | {lat}, {lon}")

# ---- ОТ: один запрос, два полигона 20/40 -----------------------------------
pt_features = []
try:
    r = isochrone(lat=lat, lon=lon, durations=[1200, 2400], transport="public_transport",
                  start_time=msk_to_utc(DATE, "08:30"))
    if r["status"] == 200 and isinstance(r["data"], dict):
        geoms = [shapely_wkt.loads(i["geometry"]) for i in r["data"].get("isochrones", [])]
        geoms.sort(key=lambda g: g.area)
        for g, minutes in zip(geoms, (20, 40)):
            valid = g.is_valid
            if not valid:
                g = g.buffer(0)
            pt_features.append({
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
        print(f"pt: 20/40 ok{' (кэш)' if r.get('cached') else ''}")
    else:
        print(f"pt: статус {r['status']} — пропуск")
except QuotaExhaustedError as e:
    print("СТОП по лимиту (pt):", e)

# ---- АВТО: два запроса 20/40 (reverse) --------------------------------------
car_features = []
try:
    for minutes in (20, 40):
        dep_min = 8 * 60 + 30 - minutes
        h, mm = divmod(dep_min, 60)
        start = msk_to_utc(DATE, f"{h:02d}:{mm:02d}")
        r = isochrone(lat=lat, lon=lon, durations=[minutes * 60], transport="driving",
                      reverse=True, start_time=start)
        if r["status"] != 200 or not isinstance(r["data"], dict):
            print(f"car {minutes}м: статус {r['status']} — пропуск")
            continue
        iso = r["data"].get("isochrones", [])
        if len(iso) != 1:
            print(f"car {minutes}м: ожидали 1 полигон, получено {len(iso)} — пропуск")
            continue
        g = shapely_wkt.loads(iso[0]["geometry"])
        valid = g.is_valid
        if not valid:
            g = g.buffer(0)
        car_features.append({
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
        print(f"car {minutes:2}м ok{' (кэш)' if r.get('cached') else ''}")
except QuotaExhaustedError as e:
    print("СТОП по лимиту (car):", e)

# ---- мерж -------------------------------------------------------------------
for out_name, features in (("pt_zones.geojson", pt_features), ("car_zones.geojson", car_features)):
    out = ROOT / "data" / "out" / out_name
    zones = json.loads(out.read_text(encoding="utf-8"))
    keys_new = {(f["properties"]["school_id"], f["properties"]["min"]) for f in features}
    kept = [f for f in zones["features"]
            if (f["properties"]["school_id"], f["properties"]["min"]) not in keys_new]
    zones["features"] = kept + features
    out.write_text(json.dumps(zones, ensure_ascii=False), encoding="utf-8")
    print(f"{out_name}: {len(zones['features'])} полигонов (заменено {len(features)}, "
          f"удалено старых {len(kept) - len(zones['features']) + len(features)})")
