"""Линии московского метро из OSM (Overpass API) → data/out/metro_lines.geojson.

relation route=subway в bbox Москвы, out geom. Каждый relation = линия (цвет/имя из
тегов colour/ref/name). Упрощение shapely (tolerance ~15 м) для размера. ODbL —
атрибуция OSM уже есть на карте. Офлайн-встраивание во вьюер: рантайм ничего не грузит.
"""
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from shapely.geometry import LineString
from shapely import simplify, to_geojson

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "out" / "metro_lines.geojson"

OVERPASS_MIRRORS = [
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]
QUERY = ('[out:json][timeout:150];'
         '(relation["route"="subway"](55.5,37.25,56.0,38.0););'
         'out geom;')

data = None
for url in OVERPASS_MIRRORS:
    try:
        req = urllib.request.Request(url, data=QUERY.encode("utf-8"),
                                     headers={"User-Agent": "school-transport/0.1 (metro lines)"})
        with urllib.request.urlopen(req, timeout=200) as r:
            data = json.loads(r.read().decode("utf-8"))
        print("зеркало сработало:", url)
        break
    except Exception as e:
        print("зеркало не сработало:", url, "→", type(e).__name__, getattr(e, "code", ""))
if data is None:
    raise SystemExit("СТОП: все зеркала Overpass недоступны")

relations = [e for e in data.get("elements", []) if e.get("type") == "relation"]
print("relations route=subway:", len(relations))

FALLBACK_COLOURS = {"1": "#e53935", "2": "#43a047", "3": "#1e88e5", "4": "#00acc1",
                    "5": "#8e5b2d", "6": "#f48fb1", "7": "#c2185b", "8": "#fdd835",
                    "9": "#8d6e63", "10": "#9ccc65", "11": "#00bcd4", "12": "#78909c",
                    "13": "#7cb8f7", "14": "#ff7043", "15": "#e91e63", "16": "#66bb6a"}

features = []
for rel in relations:
    tags = rel.get("tags", {})
    name = tags.get("name", "")
    ref = tags.get("ref", "")
    colour = tags.get("colour") or FALLBACK_COLOURS.get(ref, "#9e9e9e")
    # собираем точки member-ways по порядку; разрыв > ~3 км → новая линия
    lines, cur = [], []
    for m in rel.get("members", []):
        if m.get("type") != "way":
            continue
        pts = [(p["lon"], p["lat"]) for p in m.get("geometry", []) if p.get("lat") is not None]
        if not pts:
            continue
        if cur and ((cur[-1][0] - pts[0][0]) ** 2 + (cur[-1][1] - pts[0][1]) ** 2) ** 0.5 > 0.03:
            lines.append(cur)
            cur = []
        cur.extend(pts)
    if cur:
        lines.append(cur)
    for i, pts in enumerate(lines):
        if len(pts) < 2:
            continue
        g = simplify(LineString(pts), tolerance=0.00015, preserve_topology=True)
        features.append({
            "type": "Feature",
            "properties": {"name": name, "ref": ref, "colour": colour,
                           "part": i + 1 if len(lines) > 1 else None},
            "geometry": json.loads(to_geojson(g)),
        })

OUT.write_text(json.dumps({"type": "FeatureCollection", "features": features},
                           ensure_ascii=False), encoding="utf-8")
print(f"линий собрано: {len(features)} ({OUT.stat().st_size // 1024} КБ)")
by_ref = {}
for f in features:
    by_ref.setdefault(f["properties"]["ref"] or "без ref", 0)
    by_ref[f["properties"]["ref"] or "без ref"] += 1
print("по ref:", dict(sorted(by_ref.items(), key=lambda x: x[0])))
print("сохранено:", OUT)
