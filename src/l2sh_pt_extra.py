"""Л2Ш приоритет (09.10): зоны ОТ 25/30/35 мин — ОДИН изохронный запрос, мерж в pt_zones.geojson.

durations=[1500,1800,2100] одним запросом (start_time один — 05:30Z, как у Стадии 5).
Сортировка изохрон по полю duration (не по площади). Мерж идемпотентен:
существующие фичи (school_id+min) заменяются, остальные школы не трогаются.
"""
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import yaml
from shapely import wkt as shapely_wkt, to_geojson
from client import isochrone, msk_to_utc

ROOT = Path(__file__).resolve().parent.parent
CFG = yaml.safe_load((ROOT / "config" / "experiment.yaml").read_text(encoding="utf-8"))
DATE = CFG["date"]
L2SH = "лицей-вторая-школа-в-ф-овчинникова"
OUT = ROOT / "data" / "out" / "pt_zones.geojson"

lat = lon = name = None
with open(ROOT / "config" / "schools.csv", encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        if r["entity_id"] == L2SH:
            lat, lon, name = float(r["lat"]), float(r["lon"]), r["name"]
            break
if lat is None:
    raise SystemExit("Л2Ш не найдена в schools.csv")

start = msk_to_utc(DATE, "08:30")
r = isochrone(lat=lat, lon=lon, durations=[1500, 1800, 2100],
              transport="public_transport", start_time=start)
print("статус:", r["status"], "| кэш:", r.get("cached"))
if r["status"] != 200 or not isinstance(r["data"], dict):
    raise SystemExit(f"СТОП: iso pt Л2Ш status={r['status']} — данные НЕ записаны")

iso = sorted(r["data"].get("isochrones", []), key=lambda i: i.get("duration", 10**9))
want = {1500: 25, 1800: 30, 2100: 35}
features = []
for i in iso:
    d = i.get("duration")
    if d not in want:
        print(f"  неожиданная duration={d} — пропуск")
        continue
    g = shapely_wkt.loads(i["geometry"])
    valid = g.is_valid
    if not valid:
        g = g.buffer(0)
    features.append({
        "type": "Feature",
        "properties": {
            "school_id": L2SH, "name": name, "min": want[d], "mode": "public_transport",
            "method": "isochrone pt reverse:false",
            "status": "approx: зона «от школы»; ошибка направления — Стадия 4",
            "start_time": start, "request_hash": r.get("request_hash"),
            "was_invalid": not valid,
        },
        "geometry": json.loads(to_geojson(g)),
    })

if len(features) != 3:
    raise SystemExit(f"СТОП: получено {len(features)}/3 полигонов")

zones = json.loads(OUT.read_text(encoding="utf-8"))
old = [f for f in zones["features"]
       if not (f["properties"]["school_id"] == L2SH and f["properties"]["min"] in (25, 30, 35))]
print(f"мерж: было {len(zones['features'])} фич, вытеснено старых Л2Ш 25/30/35: "
      f"{len(zones['features']) - len(old)}")
zones["features"] = old + features
OUT.write_text(json.dumps(zones, ensure_ascii=False), encoding="utf-8")
print(f"pt_zones.geojson: {len(zones['features'])} фич (+3 Л2Ш 25/30/35)")
