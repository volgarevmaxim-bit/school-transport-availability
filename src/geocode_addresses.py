"""Геокодинг 3 адресов владельца (09.10) → config/addresses.csv + data/out/addresses.geojson.

Счётчик geocoder свежий (0/50). Контроль качества: печатаем name/full_name/purpose
каждого результата — сверка с ожидаемыми районами вручную по выводу.
"""
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from client import geocode

ROOT = Path(__file__).resolve().parent.parent

ADDRESSES = [
    ("lp-55", "ЛП-55", "Москва, Ленинский проспект, 55/1 стр. 1"),
    ("siti", "Сити", "Москва, Пресненская набережная, 10"),
    ("kurchatnik", "Курчатник", "Москва, площадь Академика Курчатова, 1"),
]

rows, feats = [], []
for aid, label, addr in ADDRESSES:
    r = geocode(addr, fields="items.point,items.name,items.full_name,items.purpose_name,items.address_name")
    print(f"\n=== {label} ({addr}) ===")
    print("статус:", r["status"], "| кэш:", r.get("cached"))
    if r["status"] != 200 or not isinstance(r["data"], dict):
        print("  геокодинг не удался — пропуск")
        continue
    items = (r["data"].get("result") or {}).get("items", [])
    if not items:
        print("  пустой результат — пропуск")
        continue
    it = items[0]
    name = it.get("name")
    full = it.get("full_name") or {}
    full_name = full.get("name") if isinstance(full, dict) else full
    point = it.get("point") or {}
    lat, lon = point.get("lat"), point.get("lon")
    print(f"  name: {name}")
    print(f"  full_name: {full_name}")
    print(f"  purpose: {it.get('purpose_name')} | address_name: {it.get('address_name')}")
    print(f"  point: lat={lat} lon={lon}")
    if lat is None or lon is None:
        print("  нет точки — пропуск")
        continue
    rows.append({"id": aid, "label": label, "address": addr,
                 "name": name, "full_name": full_name,
                 "lat": lat, "lon": lon, "request_hash": r.get("request_hash")})
    feats.append({"type": "Feature",
                  "properties": {"address_id": aid, "label": label, "name": name,
                                 "full_name": full_name, "address": addr},
                  "geometry": {"type": "Point", "coordinates": [lon, lat]}})

csv_path = ROOT / "config" / "addresses.csv"
with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=["id", "label", "address", "name", "full_name", "lat", "lon"])
    w.writeheader()
    for r in rows:
        w.writerow({k: r.get(k, "") for k in w.fieldnames})
geo_path = ROOT / "data" / "out" / "addresses.geojson"
geo_path.write_text(json.dumps({"type": "FeatureCollection", "features": feats},
                               ensure_ascii=False), encoding="utf-8")

print(f"\nадресов загеокодировано: {len(rows)}/3")
print("CSV:", csv_path)
print("GeoJSON:", geo_path)
print("ПРОВЕРКА координат (ожидания): ЛП-55 ~55.708,37.58 (пл. Гагарина) | "
      "Сити ~55.7507,37.5400 | Курчатник ~55.8017,37.476 (Щукино)")
