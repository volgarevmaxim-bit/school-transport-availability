"""Стадия 3: работает ли reverse:true для public_transport, допустимые типы, влияние расписания.

5 изохрон ОТ по Л2Ш (1200 с): reverse:true / без reverse / types [metro] / types [metro,mcc,mcd]
/ вечер 20:00Z. Сравнение площадей, IoU, числа частей MULTIPOLYGON (лучи) и «нитевидности»
(boundary/area).
"""
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import yaml
from shapely import wkt as shapely_wkt
from shapely import to_geojson
from client import _request, BASE_URLS, msk_to_utc

ROOT = Path(__file__).resolve().parent.parent
CFG = yaml.safe_load((ROOT / "config" / "experiment.yaml").read_text(encoding="utf-8"))
DATE = CFG["date"]
L2SH = (55.69799, 37.55644)  # CSV-координаты Л2Ш


def iso_pt(*, reverse=None, types=None, start_time=None):
    body = {"start": {"lat": L2SH[0], "lon": L2SH[1]}, "durations": [1200],
            "transport": "public_transport", "format": "wkt"}
    if reverse is not None:      # эксперимент: отправляем reverse для ОТ вопреки докам
        body["reverse"] = bool(reverse)
    if types:
        body["public_transport_types"] = types
    if start_time:
        body["start_time"] = start_time
    return _request("isochrone", BASE_URLS["isochrone"], json.dumps(body, sort_keys=True))


def stats(tag, r):
    print(f"[{tag}] status={r['status']}", "(кэш)" if r.get("cached") else "")
    if r["status"] != 200 or not isinstance(r["data"], dict):
        print("   тело:", str(r["data"])[:250])
        return None
    g = shapely_wkt.loads(r["data"]["isochrones"][0]["geometry"])
    lat = g.centroid.y
    area = g.area * 111.32 * 111.32 * math.cos(math.radians(lat))
    nparts = len(g.geoms) if g.geom_type == "MultiPolygon" else 1
    bl = g.boundary.length * 111.32
    print(f"   площадь {area:.1f} км² | частей {nparts} | периметр/√площадь {bl/math.sqrt(g.area):.0f}")
    return g


print("DATE:", DATE)
g_rev = stats("reverse:true", iso_pt(reverse=True, start_time=msk_to_utc(DATE, "08:30")))
g_fwd = stats("без reverse", iso_pt(start_time=msk_to_utc(DATE, "08:30")))
g_metro = stats("types [metro]", iso_pt(types=["metro"], start_time=msk_to_utc(DATE, "08:30")))
g_mcc = stats("types [metro,mcc,mcd]", iso_pt(types=["metro", "mcc", "mcd"], start_time=msk_to_utc(DATE, "08:30")))
g_eve = stats("вечер 20:00Z", iso_pt(start_time="2026-10-14T20:00:00Z"))
g_mcc_only = stats("types [mcc] отдельно", iso_pt(types=["mcc"], start_time=msk_to_utc(DATE, "08:30")))

pairs = [("rev vs fwd", g_rev, g_fwd), ("metro vs все", g_metro, g_fwd),
         ("mcc/mcd vs metro", g_mcc, g_metro), ("вечер vs утро", g_eve, g_fwd),
         ("mcc отдельно vs metro", g_mcc_only, g_metro)]
print("\nПопарные сравнения (IoU):")
for name, a, b in pairs:
    if a is None or b is None:
        print(f"  {name}: пропуск (ошибка)"); continue
    iou = a.intersection(b).area / max(a.union(b).area, 1e-12)
    print(f"  {name}: IoU={iou:.3f}")

# сохранить геометрии для визуального разбора в Стадии 7
out = ROOT / "data" / "out" / "stage3_pt.geojson"
feats = []
for tag, g in (("reverse:true", g_rev), ("no_reverse", g_fwd), ("metro", g_metro),
               ("metro_mcc_mcd", g_mcc), ("evening", g_eve), ("mcc_only", g_mcc_only)):
    if g is not None:
        feats.append({"type": "Feature",
                      "properties": {"tag": tag, "mode": "public_transport", "min": 20},
                      "geometry": json.loads(to_geojson(g))})
out.write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False), encoding="utf-8")
print("сохранено:", out)
