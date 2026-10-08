"""Пробы Стадии 0: проверка ключа на всех сервисах + кэш + эндпоинты.

Каждая проба — один бюджетный запрос (кроме проверки кэша). Вывод компактный,
ключ нигде не печатается.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import yaml
from client import (geocode, isochrone, directions_driving, public_transport_route,
                    distance_matrix, static_map, msk_to_utc, msk_to_unix, budget_report)

CFG = yaml.safe_load(Path(__file__).resolve().parent.parent.joinpath("config", "experiment.yaml").read_text(encoding="utf-8"))
DATE = CFG["date"]

L2SH = (55.6979, 37.5564)   # ул. Фотиевой, 18
LIT = (55.6923, 37.5437)    # Ломоносовский, 16
S1514 = (55.6631, 37.5326)  # Челомея, 6А


def show(tag, r):
    extra = ""
    if r.get("cached"):
        extra = " (ИЗ КЭША — бюджет не тратился)"
    print(f"[{tag}] status={r['status']}{extra}")


print("== 1. geocode (повтор для унификации кэша) ==")
r1 = geocode("Москва, проспект Ломоносовский, 16")
show("geocode", r1)
if r1["status"] == 200:
    items = r1["data"].get("result", {}).get("items", [])
    print("   первый результат:", items[0].get("full_name") if items else "-")
r1b = geocode("Москва, проспект Ломоносовский, 16")
show("geocode-повтор", r1b)

print("== 2. isochrone driving, 600 c, reverse false ==")
r2 = isochrone(lat=L2SH[0], lon=L2SH[1], durations=[600], transport="driving",
               reverse=False, start_time=msk_to_utc(DATE, "08:10"))
show("iso-driving", r2)
if r2["status"] == 200 and isinstance(r2["data"], dict):
    iso = r2["data"].get("isochrones", [])
    print("   status-поля:", r2["data"].get("status"), "| полигонов:", len(iso),
          "| wkt-длина:", len(iso[0]["geometry"]) if iso else "-")

print("== 3. isochrone public_transport, 600 c ==")
r3 = isochrone(lat=L2SH[0], lon=L2SH[1], durations=[600], transport="public_transport",
               start_time=msk_to_utc(DATE, "08:30"))
show("iso-pt", r3)
if r3["status"] == 200 and isinstance(r3["data"], dict):
    iso = r3["data"].get("isochrones", [])
    print("   status-поля:", r3["data"].get("status"), "| полигонов:", len(iso),
          "| wkt-длина:", len(iso[0]["geometry"]) if iso else "-")
else:
    print("   тело (первые 200):", str(r3["data"])[:200])

print("== 4. routing/7.0.0 driving, statistics ==")
r4 = directions_driving(f"{LIT[1]},{LIT[0]}", f"{L2SH[1]},{L2SH[0]}",
                        utc_unix=msk_to_unix(DATE, "08:10"), traffic_mode="statistics")
show("routing7", r4)
if r4["status"] == 200 and isinstance(r4["data"], dict):
    res = r4["data"].get("result", [])
    if res:
        r0 = res[0]
        print("   ключи result[0]:", sorted(r0.keys())[:14])
        print("   total_duration:", r0.get("total_duration"), "| total_distance:", r0.get("total_distance"))
    else:
        print("   result пуст, meta/message:", r4["data"].get("message"), str(r4["data"].get("meta"))[:100])

print("== 5. public_transport/2.0, enable_schedule ==")
r5 = public_transport_route(f"{LIT[1]},{LIT[0]}", f"{L2SH[1]},{L2SH[0]}",
                            start_time_unix=msk_to_unix(DATE, "08:30"), enable_schedule=True)
show("pt2", r5)
if r5["status"] == 200 and isinstance(r5["data"], dict):
    items = r5["data"].get("result", {}).get("items", []) if isinstance(r5["data"].get("result"), dict) else []
    if items:
        it = items[0]
        print("   ключи items[0]:", sorted(it.keys()))
        print("   total_duration:", it.get("total_duration"), "| transfer_count:", it.get("transfer_count"),
              "| movement_duration:", it.get("movement_duration"))
        legs = it.get("legs", [])
        print("   участков:", len(legs), "| время первого-последнего:", 
              legs[0].get("departure") if legs else "-", "->", legs[-1].get("arrival") if legs else "-")
    else:
        print("   items пуст:", str(r5["data"])[:300])
else:
    print("   тело:", str(r5["data"])[:300])

print("== 6. get_dist_matrix (минимальное тело) ==")
pts = [{"lat": LIT[0], "lon": LIT[1]}, {"lat": L2SH[0], "lon": L2SH[1]}, {"lat": S1514[0], "lon": S1514[1]}]
r6 = distance_matrix(pts, sources=[0], targets=[1, 2])
show("matrix", r6)
if r6["status"] == 200 and isinstance(r6["data"], dict):
    print("   ключи:", sorted(r6["data"].keys()))
    rows = r6["data"].get("rows", [])
    if rows:
        print("   rows[0]:", rows[0])
else:
    print("   тело:", str(r6["data"])[:300])

print("== 7. static maps: маркер + линия + ПОЛИГОН (pn) ==")
r7 = static_map(f"{L2SH[0]},{L2SH[1]}", zoom=13, size="600x400",
                markers=f"{L2SH[0]},{L2SH[1]}~k:c",
                polylines=f"{LIT[0]},{LIT[1]},{L2SH[0]},{L2SH[1]}~c:0000ff~w:4",
                polygons=f"{L2SH[0]-0.005},{L2SH[1]-0.005},{L2SH[0]+0.005},{L2SH[1]-0.005},{L2SH[0]+0.005},{L2SH[1]+0.005},{L2SH[0]-0.005},{L2SH[1]+0.005}~c:ff0000~f:ff000044")
show("static", r7)
if r7["status"] == 200 and isinstance(r7["data"], bytes):
    out = Path(__file__).resolve().parent.parent / "reports" / "plots" / "stage0_probe.png"
    out.write_bytes(r7["data"])
    print("   PNG сохранён:", out, "| байт:", len(r7["data"]))
else:
    print("   тело:", str(r7["data"])[:200])

print()
print("== БЮДЖЕТ ==")
for s, b in budget_report().items():
    print(f"   {s}: потрачено {b['spent']}, остаток {b['remaining']}")
