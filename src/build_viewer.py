"""Генератор самодостаточного HTML-вьюера зон и лепестков (Leaflet, данные встроены).

Селекторы: школа / время (20, 40, обе) / режим (ОТ; авто добавится при появлении car_zones).
Чекбокс «лепестки». Данные встраиваются в HTML — файл можно открыть двойным кликом (нужен
интернет для подложки OSM; сами полигоны работают и без него на сером фоне).
"""
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "out"

# (ключ режима, подпись, файл зон, файл лепестков)
DATASETS = [("pt", "Общественный транспорт", OUT / "pt_zones.geojson", OUT / "lobes_pt.geojson")]

schools = {}
with open(ROOT / "config" / "schools.csv", encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        if r["selected"] == "1":
            schools[r["entity_id"]] = {"name": r["name"], "lat": float(r["lat"]), "lon": float(r["lon"])}

zones, lobes = {}, {}
for key, label, zf, lf in DATASETS:
    if zf.exists():
        zones[key] = json.loads(zf.read_text(encoding="utf-8"))
    if lf.exists():
        lobes[key] = json.loads(lf.read_text(encoding="utf-8"))

mode_options = "".join(f'<option value="{k}">{v}</option>' for k, v, _, _ in DATASETS)
school_json = json.dumps(schools, ensure_ascii=False)
zones_json = json.dumps(zones, ensure_ascii=False)
lobes_json = json.dumps(lobes, ensure_ascii=False)

html = """<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Доступность школ — зоны и лепестки</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<style>
html,body{height:100%;margin:0;font-family:"Segoe UI",sans-serif}
#map{height:100%}
#bar{position:absolute;top:8px;left:8px;z-index:1000;background:#fff;padding:7px 10px;
border-radius:8px;box-shadow:0 1px 6px rgba(0,0,0,.35);font-size:13px;max-width:calc(100% - 20px)}
#bar select{padding:2px 4px;margin-right:10px}
#bar label{margin-right:12px;white-space:nowrap}
#info{color:#555}
.legend{position:absolute;bottom:20px;right:10px;z-index:1000;background:#fff;padding:6px 9px;
border-radius:6px;box-shadow:0 1px 5px rgba(0,0,0,.3);font-size:12px;line-height:1.6}
.sw{display:inline-block;width:14px;height:10px;border:1px solid #999;margin-right:5px}
</style></head><body>
<div id="bar">
Школа <select id="school"></select>
Время <select id="minutes">
<option value="20">20 мин</option><option value="40" selected>40 мин</option>
<option value="both">20 и 40</option></select>
Режим <select id="mode">__MODE_OPTIONS__</select>
<label><input type="checkbox" id="showLobes" checked>лепестки</label>
<span id="info"></span>
</div>
<div id="map"></div>
<div class="legend">
<div><span class="sw" style="background:#2b7bba"></span>зона 20 мин</div>
<div><span class="sw" style="background:#e6772e"></span>зона 40 мин</div>
<div><span class="sw" style="background:#d62728"></span>лепесток (выступ)</div>
<div><span class="sw" style="background:#999;border-radius:50%"></span>школа</div>
</div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const SCHOOLS = __SCHOOLS__;
const ZONES = __ZONES__;
const LOBES = __LOBES__;
const COLORS = {20: '#2b7bba', 40: '#e6772e'};

const map = L.map('map').setView([55.69, 37.53], 10);
L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',
  {maxZoom: 17, attribution: '&copy; OpenStreetMap'}).addTo(map);

const schoolSel = document.getElementById('school');
Object.keys(SCHOOLS).forEach(sid => {
  const o = document.createElement('option');
  o.value = sid; o.textContent = SCHOOLS[sid].name;
  schoolSel.appendChild(o);
});

const schoolLayer = L.layerGroup().addTo(map);
Object.entries(SCHOOLS).forEach(([sid, s]) => {
  L.circleMarker([s.lat, s.lon], {radius: 4, color: '#333', weight: 1, fillColor: '#999', fillOpacity: 0.9})
    .bindTooltip(`${SCHOOLS[sid].name}`).addTo(schoolLayer);
});

const zoneLayer = L.layerGroup().addTo(map);
const lobeLayer = L.layerGroup().addTo(map);

function esc(s){return String(s).replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}

function render(){
  const sid = schoolSel.value, mins = document.getElementById('minutes').value;
  const mode = document.getElementById('mode').value, showLobes = document.getElementById('showLobes').checked;
  zoneLayer.clearLayers(); lobeLayer.clearLayers();
  let zc = 0, lc = 0; const bounds = L.latLngBounds();

  const zds = ZONES[mode] || {features: []};
  zds.features.forEach(f => {
    const p = f.properties;
    if (sid !== 'all' && p.school_id !== sid) return;
    if (mins !== 'both' && p.min != mins) return;
    const c = COLORS[p.min] || '#555';
    L.geoJSON(f, {style: {color: c, weight: 2, fillColor: c, fillOpacity: 0.18},
      onEachFeature: (ft, lyr) => lyr.bindPopup(
        `<b>${esc(p.name)}</b><br>${p.min} мин · ${mode === 'pt' ? 'общественный транспорт' : mode}<br>${esc(p.status)}`)})
      .addTo(zoneLayer);
    bounds.extend(L.geoJSON(f).getBounds()); zc++;
  });

  if (showLobes) {
    const lds = LOBES[mode] || {features: []};
    lds.features.forEach(f => {
      const p = f.properties;
      if (sid !== 'all' && p.school_id !== sid) return;
      if (mins !== 'both' && p.min != mins) return;
      L.geoJSON(f, {style: {color: '#d62728', weight: 2, fillColor: '#d62728', fillOpacity: 0.35, dashArray: '4 2'},
        onEachFeature: (ft, lyr) => lyr.bindPopup(
          `<b>Лепесток · ${esc(p.school_id.slice(0, 24))}</b><br>${p.min} мин · азимут ${p.azimuth}°<br>` +
          `дальность ${p.r_max_km} км · вытянутость ${p.elongation}<br>площадь ${p.area_km2} км² (${(p.zone_share*100).toFixed(1)}% зоны)`)})
        .addTo(lobeLayer);
      bounds.extend(L.geoJSON(f).getBounds()); lc++;
    });
  }

  if (bounds.isValid()) map.fitBounds(bounds, {padding: [30, 30], maxZoom: 12});
  document.getElementById('info').textContent = `зон: ${zc}, лепестков: ${lc}`;
}

schoolSel.addEventListener('change', render);
document.getElementById('minutes').addEventListener('change', render);
document.getElementById('mode').addEventListener('change', render);
document.getElementById('showLobes').addEventListener('change', render);

// вариант «все школы» в начало списка
const o = document.createElement('option');
o.value = 'all'; o.textContent = '— все школы —';
schoolSel.insertBefore(o, schoolSel.firstChild);
render();
</script></body></html>
"""

html = (html.replace("__MODE_OPTIONS__", mode_options)
            .replace("__SCHOOLS__", school_json)
            .replace("__ZONES__", zones_json)
            .replace("__LOBES__", lobes_json))

dest = OUT / "zones_viewer.html"
dest.write_text(html, encoding="utf-8")
print("вьюер:", dest, f"({dest.stat().st_size//1024} КБ)")
print("школ:", len(schools), "| режимов:", len(DATASETS), "| зон:", sum(len(z['features']) for z in zones.values()),
      "| лепестков:", sum(len(l['features']) for l in lobes.values()))
