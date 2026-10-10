"""Сравнение лепестков ОТ vs авто (гипотеза владельца 09.10).

Кандидат «дешёвый район — быстрый доступ» = лепесток ОТ, у которого НЕТ авто-лепестка
в пересекающемся секторе: |az_ot − az_car|(mod 360) < (w_ot + w_car)/2.
Сравнение только при одинаковых минутах зоны (20/25/30/35/40).
Выход: data/out/ot_only_lobes.csv + сводка в консоль. 0 запросов API.
"""
import csv
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "out"

pt = json.loads((OUT / "lobes_pt.geojson").read_text(encoding="utf-8"))["features"]
car = json.loads((OUT / "lobes_car.geojson").read_text(encoding="utf-8"))["features"]


def ang_diff(a, b):
    d = abs(a - b) % 360
    return min(d, 360 - d)


def car_lobe_in_sector(sid, minutes, az, width):
    for f in car:
        p = f["properties"]
        if p["school_id"] != sid or p["min"] != minutes:
            continue
        if ang_diff(az, p["azimuth"]) < (width + p["width_deg"]) / 2:
            return True
    return False


rows = []
for f in pt:
    p = f["properties"]
    if car_lobe_in_sector(p["school_id"], p["min"], p["azimuth"], p["width_deg"]):
        continue
    rows.append(p)

schools = {}
with open(ROOT / "config" / "schools.csv", encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        schools[r["entity_id"]] = r["name"]

out_csv = OUT / "ot_only_lobes.csv"
with open(out_csv, "w", newline="", encoding="utf-8-sig") as f:
    if rows:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

print(f"лепестков ОТ: {len(pt)}, авто: {len(car)}")
print(f"кандидатов «только у ОТ»: {len(rows)}")
print()
for r in sorted(rows, key=lambda x: -x["r_max_km"]):
    name = schools.get(r["school_id"], r["school_id"])
    print(f"  {name[:40]:42} {r['min']:2}м аз={r['azimuth']:6.1f}° "
          f"ш={r['width_deg']:2}° r={r['r_max_km']:5.2f}км выт={r['elongation']:4.1f}")
print("\nCSV:", out_csv)
