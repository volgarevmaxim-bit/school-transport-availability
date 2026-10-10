"""Нормализация линий метро: lineId → name/colour (официальная схема ММ).

Источник геометрии: rudney5000/moscow-metro-isochrone public/data/lines.geojson
(ODbL, OSM-производные; атрибуция OSM уже в подложке вьюера).
Вход: data/out/metro_test.geojson → выход: data/out/metro_lines.geojson.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "out"

LINE_INFO = {
    "1":   ("Сокольническая", "#EF161E"),
    "2":   ("Замоскворецкая", "#4DBE52"),
    "3":   ("Арбатско-Покровская", "#0078BE"),
    "4":   ("Филёвская", "#00A2DC"),
    "4A":  ("Филёвская (вилка)", "#00A2DC"),
    "5":   ("Кольцевая", "#9A6B2A"),
    "6":   ("Калужско-Рижская", "#F07E24"),
    "7":   ("Таганско-Краснопресненская", "#A71965"),
    "8":   ("Калининская", "#FFD702"),
    "8A":  ("Солнцевская", "#FFD702"),
    "8KS": ("Калининско-Солнцевская", "#FFD702"),
    "9":   ("Серпуховско-Тимирязевская", "#909197"),
    "10":  ("Люблинско-Дмитровская", "#9ACD32"),
    "11":  ("Большая кольцевая", "#82C0C0"),
    "11A": ("Каховская", "#82C0C0"),
    "11K": ("Каховская (сегмент)", "#82C0C0"),
    "12":  ("Бутовская", "#A6B7D4"),
    "13":  ("Монорельс", "#0066B3"),
    "14":  ("МЦК", "#F32735"),
    "15":  ("Некрасовская", "#D77AAB"),
    "16":  ("Троицкая", "#78B0A0"),
    "17":  ("Рублёво-Архангельская", "#78909C"),
}

src = json.loads((OUT / "metro_test.geojson").read_text(encoding="utf-8"))
features = []
for f in src["features"]:
    lid = f["properties"].get("lineId", "")
    name, colour = LINE_INFO.get(lid, (f"линия {lid}", "#9e9e9e"))
    features.append({
        "type": "Feature",
        "properties": {"line_id": lid, "name": name, "colour": colour},
        "geometry": f["geometry"],
    })
(OUT / "metro_lines.geojson").write_text(
    json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False),
    encoding="utf-8")
(OUT / "metro_test.geojson").unlink(missing_ok=True)
print(f"metro_lines.geojson: {len(features)} линий")
