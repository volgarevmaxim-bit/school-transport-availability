"""Генератор самодостаточного HTML-вьюера зон/лепестков + аналитика (Leaflet + turf, данные встроены).

Верхняя панель: школа (поиск) / время 20–40 / режим ОТ-авто / чекбоксы «лепестки», «метро».
Нижняя панель «Аналитика»: СКЛАДНАЯ (ручка-таб, по умолчанию свёрнута — тап раскрывает/убирает).
Внутри: чекбоксы 20 школ + 3 адресов, тумблер «сценарий пересечения» (turf.js), кнопки все/снять.
Выделение: выбранная школа (верхний поиск) и отмеченные чекбоксами школы — тёмные кружки.
Мобильная вёрстка: селектор школ сдвинут на 16pt вправо (не залезает под кнопки зума).
Линии метро (OSM, ODbL) встроены, слой под зонами, чекбокс «метро».
"""
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "out"

# (ключ режима, подпись, файл зон, файл лепестков)
DATASETS = [("pt", "Общественный транспорт", OUT / "pt_zones.geojson", OUT / "lobes_pt.geojson"),
            ("car", "Автомобиль", OUT / "car_zones.geojson", OUT / "lobes_car.geojson")]

schools = {}
with open(ROOT / "config" / "schools.csv", encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        if r["selected"] == "1":
            schools[r["entity_id"]] = {"name": r["name"], "lat": float(r["lat"]), "lon": float(r["lon"])}

addrs = {}
with open(ROOT / "config" / "addresses.csv", encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        addrs[r["id"]] = {"label": r["label"], "name": r["name"], "address": r["address"],
                          "lat": float(r["lat"]), "lon": float(r["lon"])}

buildings = {}
bf = ROOT / "config" / "buildings.csv"
if bf.exists():
    with open(bf, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if r.get("lat") and r.get("lon"):
                buildings[r["point_id"]] = {
                    "school_id": r["school_id"], "name": r["name"],
                    "address": r.get("address", ""), "role": r.get("role", ""),
                    "lat": float(r["lat"]), "lon": float(r["lon"]),
                    "is_base": r.get("is_base", "") == "1"}
# на случай, если is_base не проставлен в CSV: базовым считаем корпус на координатах школы
for pid, b in buildings.items():
    s = schools.get(b["school_id"])
    if s and abs(b["lat"] - s["lat"]) < 1e-5 and abs(b["lon"] - s["lon"]) < 1e-5:
        b["is_base"] = True

zones, lobes, zones_addr = {}, {}, {}
for key, label, zf, lf in DATASETS:
    if zf.exists():
        zones[key] = json.loads(zf.read_text(encoding="utf-8"))
    if lf.exists():
        lobes[key] = json.loads(lf.read_text(encoding="utf-8"))
for key, label, _, _ in DATASETS:
    zaf = OUT / f"address_zones_{key}.geojson"
    if zaf.exists():
        zones_addr[key] = json.loads(zaf.read_text(encoding="utf-8"))

metro_file = OUT / "metro_lines.geojson"
metro = json.loads(metro_file.read_text(encoding="utf-8")) if metro_file.exists() else {"features": []}

mode_options = "".join(f'<option value="{k}">{v}</option>' for k, v, _, _ in DATASETS)
school_json = json.dumps(schools, ensure_ascii=False)
addr_json = json.dumps(addrs, ensure_ascii=False)
buildings_json = json.dumps(buildings, ensure_ascii=False)
zones_json = json.dumps(zones, ensure_ascii=False)
zones_addr_json = json.dumps(zones_addr, ensure_ascii=False)
lobes_json = json.dumps(lobes, ensure_ascii=False)
metro_json = json.dumps(metro, ensure_ascii=False)

checkbox_items = []
for sid, s in schools.items():
    checkbox_items.append(f'<div class="aitem"><label><input type="checkbox" class="ichk" value="school:{sid}">'
                          f'<span class="aname">{s["name"]}</span></label></div>')
for aid, a in addrs.items():
    checkbox_items.append(f'<div class="aitem aaddr"><label><input type="checkbox" class="ichk" value="addr:{aid}">'
                          f'<span class="abull">●</span><span class="aname">{a["label"]}</span>'
                          f'<span class="asub">{a["address"]}</span></label></div>')
checkbox_html = "\n".join(checkbox_items)

html = """<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Доступность школ — зоны и лепестки</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<style>
html,body{height:100%;margin:0;font-family:"Segoe UI",sans-serif}
#wrap{display:flex;flex-direction:column;height:100%}
#map{flex:1;position:relative;min-height:0}
#bar{background:#fff;padding:7px 10px;font-size:13px;border-bottom:1px solid #ddd}
#bar select{padding:2px 4px;margin-right:10px}
#bar label{margin-right:12px;white-space:nowrap}
#info{color:#555}
#schoolWrap{position:relative;display:inline-block;vertical-align:middle}
#school{width:250px;padding:3px 6px;border:1px solid #999;border-radius:4px;font-size:13px}
#schoolList{position:absolute;top:100%;left:0;right:0;margin-top:2px;background:#fff;
border:1px solid #ccc;border-radius:4px;max-height:260px;overflow:auto;z-index:1100;
box-shadow:0 2px 8px rgba(0,0,0,.25);display:none}
.sitem{padding:4px 8px;cursor:pointer;font-size:13px;white-space:nowrap}
.sitem:hover{background:#eef3fb}
@media (max-width: 640px){
  #schoolWrap{margin-left:16pt}
  #school{width:170px}
}
#anaTab{height:24px;line-height:24px;text-align:center;background:#eef1f4;border-top:1px solid #ccc;
cursor:pointer;font-size:12px;user-select:none;-webkit-user-select:none;color:#333}
#anaTab:hover{background:#e2e7ec}
#analytics{height:150px;display:flex;background:#fff;border-top:1px solid #ccc;font-size:12px;
overflow:hidden;transition:height .15s}
#analytics.collapsed{height:0;border-top:none}
#anaLeft{flex:1;overflow-y:auto;padding:4px 8px}
.aitem{white-space:nowrap;line-height:1.55}
.aitem label{cursor:pointer}
.aname{vertical-align:middle}
.aaddr{color:#a03}
.asub{color:#999;margin-left:6px}
.abull{color:#c0392b;font-weight:bold;margin-right:3px}
#anaRight{width:250px;padding:8px 10px;border-left:1px solid #ccc;overflow-y:auto}
#anaRight h3{margin:0 0 6px;font-size:12px}
#anaRight .row{margin:4px 0}
#anaRight button{margin-right:6px;padding:1px 8px;font-size:12px}
#interInfo{margin-top:6px;color:#333}
#interInfo .empty{color:#a33}
.legend{position:absolute;bottom:20px;right:10px;z-index:1000;background:#fff;padding:6px 9px;
border-radius:6px;box-shadow:0 1px 5px rgba(0,0,0,.3);font-size:12px;line-height:1.6}
.sw{display:inline-block;width:14px;height:10px;border:1px solid #999;margin-right:5px}
.swmetro{display:inline-block;width:16px;height:3px;margin-right:3px;vertical-align:middle}
</style></head><body>
<div id="wrap">
<div id="bar">
Школа <span id="schoolWrap"><input id="school" placeholder="все школы — начните набирать" autocomplete="off"><div id="schoolList"></div></span>
Время <select id="minutes">
<option value="20">20 мин</option><option value="25">25 мин</option>
<option value="30">30 мин</option><option value="35">35 мин</option>
<option value="40" selected>40 мин</option>
<option value="both">все 20–40</option></select>
Режим <select id="mode">__MODE_OPTIONS__</select>
<label><input type="checkbox" id="showLobes" checked>лепестки</label>
<label><input type="checkbox" id="showMetro" checked>метро</label>
<span id="info"></span>
</div>
<div id="map">
<div class="legend">
<div><span class="sw" style="background:#2b7bba"></span>зона 20 мин</div>
<div><span class="sw" style="background:#3fa7a0"></span>зона 25 мин</div>
<div><span class="sw" style="background:#5cb85c"></span>зона 30 мин</div>
<div><span class="sw" style="background:#f0ad4e"></span>зона 35 мин</div>
<div><span class="sw" style="background:#e6772e"></span>зона 40 мин</div>
<div><span class="sw" style="background:#d62728"></span>лепесток (выступ)</div>
<div><span class="swmetro" style="background:#EF161E"></span>линия метро</div>
<div><span class="sw" style="background:#333;border-radius:50%"></span>школа / адрес</div>
<div><span class="sw" style="background:#999;border-radius:50%"></span>корпус школы</div>
</div>
</div>
<div id="anaTab">Аналитика: пересечение областей <span id="anaArrow">▲</span></div>
<div id="analytics" class="collapsed">
<div id="anaLeft">
__CHECKBOXES__
</div>
<div id="anaRight">
<h3>Пересечение областей</h3>
<div class="row"><label><input type="checkbox" id="interOn"> сценарий вкл</label></div>
<div class="row"><button id="selAll">отметить все</button><button id="selNone">снять</button></div>
<div id="interInfo">отметьте ≥ 2 области и включите сценарий</div>
</div>
</div>
</div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://unpkg.com/@turf/turf@6/turf.min.js"></script>
<script>
const SCHOOLS = __SCHOOLS__;
const ADDRS = __ADDRS__;
const BUILDINGS = __BUILDINGS__;
const ZONES = __ZONES__;
const ZONES_ADDR = __ZONES_ADDR__;
const LOBES = __LOBES__;
const METRO = __METRO__;
const COLORS = {20: '#2b7bba', 25: '#3fa7a0', 30: '#5cb85c', 35: '#f0ad4e', 40: '#e6772e'};
const MODE_LABELS = {pt: 'общественный транспорт', car: 'автомобиль'};

const map = L.map('map').setView([55.69, 37.53], 10);
L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',
  {maxZoom: 17, attribution: '&copy; OpenStreetMap'}).addTo(map);

// линии метро — под всеми остальными слоями
const metroLayer = L.layerGroup().addTo(map);
METRO.features.forEach(f => {
  L.geoJSON(f, {interactive: true,
    style: {color: f.properties.colour || '#888', weight: 3, opacity: 0.55},
    onEachFeature: (ft, lyr) => lyr.bindTooltip(ft.properties.name)}).addTo(metroLayer);
});
document.getElementById('showMetro').addEventListener('change', e => {
  if (e.target.checked) metroLayer.addTo(map); else map.removeLayer(metroLayer);
});

let currentSchool = 'all';
const schoolInput = document.getElementById('school');
const schoolList = document.getElementById('schoolList');

function selectedSchoolIds(){
  return new Set([...document.querySelectorAll('.ichk:checked')]
    .map(cb => cb.value).filter(v => v.startsWith('school:')).map(v => v.slice(7)));
}

function updateSchoolMarkers(){
  const sel = selectedSchoolIds();
  schoolLayer.clearLayers();
  Object.entries(SCHOOLS).forEach(([sid, s]) => {
    let style;
    if (currentSchool !== 'all' && currentSchool === sid)
      style = {radius: 7, color: '#000', weight: 2, fillColor: '#111', fillOpacity: 1};
    else if (sel.has(sid))
      style = {radius: 6, color: '#222', weight: 1.5, fillColor: '#333', fillOpacity: 1};
    else
      style = {radius: 4, color: '#333', weight: 1, fillColor: '#999', fillOpacity: 0.9};
    L.circleMarker([s.lat, s.lon], style).bindTooltip(`${SCHOOLS[sid].name}`).addTo(schoolLayer);
  });
  // дополнительные корпуса (buildings.csv): подсвечиваются вместе со своей школой
  Object.entries(BUILDINGS).forEach(([pid, b]) => {
    if (b.is_base) return;
    let style;
    if (currentSchool !== 'all' && currentSchool === b.school_id)
      style = {radius: 5, color: '#000', weight: 1.5, fillColor: '#222', fillOpacity: 1};
    else if (sel.has(b.school_id))
      style = {radius: 4, color: '#222', weight: 1.5, fillColor: '#444', fillOpacity: 1};
    else
      style = {radius: 3, color: '#777', weight: 1, fillColor: '#aaa', fillOpacity: 0.85};
    const role = b.role ? ` (${b.role})` : '';
    L.circleMarker([b.lat, b.lon], style)
      .bindTooltip(`${b.name} — ${b.address}${role}`).addTo(schoolLayer);
  });
}

function selectSchool(sid){
  currentSchool = sid;
  schoolInput.value = (sid === 'all' || sid === 'none') ? '' : SCHOOLS[sid].name;
  schoolList.style.display = 'none';
  updateSchoolMarkers();
  render();
}

function showSchoolList(q){
  const query = (q || '').trim().toLowerCase();
  schoolList.innerHTML = '';
  let shown = 0;
  [['all', '— все школы —'], ['none', '— очистить (только метро) —'],
   ...Object.entries(SCHOOLS).map(([sid, s]) => [sid, s.name])].forEach(([sid, name]) => {
    if (query && !name.toLowerCase().includes(query)) return;
    const d = document.createElement('div');
    d.className = 'sitem';
    d.textContent = name;
    d.addEventListener('mousedown', e => { e.preventDefault(); selectSchool(sid); });
    schoolList.appendChild(d);
    shown++;
  });
  schoolList.style.display = shown ? 'block' : 'none';
}

schoolInput.addEventListener('input', () => showSchoolList(schoolInput.value));
schoolInput.addEventListener('focus', () => showSchoolList(schoolInput.value));
schoolInput.addEventListener('keydown', e => {
  if (e.key === 'Enter') {
    const first = schoolList.querySelector('.sitem');
    if (first) first.dispatchEvent(new MouseEvent('mousedown', {bubbles: true}));
  }
  if (e.key === 'Escape') schoolList.style.display = 'none';
});
document.addEventListener('mousedown', e => {
  if (e.target !== schoolInput && !schoolList.contains(e.target)) schoolList.style.display = 'none';
});

const schoolLayer = L.layerGroup().addTo(map);

const addrLayer = L.layerGroup().addTo(map);
const addrIcon = L.divIcon({className: '', html: '<span style="display:inline-block;width:9px;height:9px;' +
  'border-radius:50%;background:#c0392b;border:2px solid #fff;box-shadow:0 0 3px #000"></span>', iconSize: [13, 13]});

function zoneFeaturesFor(mode, key, sid, minutes){
  const src = key === 'school' ? (ZONES[mode] || {features: []}).features
                               : (ZONES_ADDR[mode] || {features: []}).features;
  const m = minutes === 'both' ? 40 : Number(minutes);
  return src.filter(f => {
    const p = f.properties;
    if (key === 'school' && p.school_id !== sid) return false;
    if (key === 'addr' && p.address_id !== sid) return false;
    if (minutes !== 'both' && p.min !== m) return false;
    return true;
  });
}

Object.entries(ADDRS).forEach(([aid, a]) => {
  L.marker([a.lat, a.lon], {icon: addrIcon})
    .bindTooltip(`${a.label}`, {direction: 'top'})
    .bindPopup(() => {
      const mode = document.getElementById('mode').value;
      const mins = document.getElementById('minutes').value;
      const m = mins === 'both' ? 40 : Number(mins);
      const inZones = [];
      Object.entries(SCHOOLS).forEach(([sid, s]) => {
        const feats = zoneFeaturesFor(mode, 'school', sid, mins);
        if (feats.length && turf.booleanPointInPolygon([a.lon, a.lat], feats[0])) inZones.push(s.name);
      });
      const list = inZones.length ? inZones.map(esc).join('<br>') : '— вне школьных зон —';
      return `<b>${esc(a.label)}</b><br>${esc(a.address)}<br><br>` +
             `В зоне ${m} мин (${MODE_LABELS[mode] || mode}):<br>${list}`;
    })
    .addTo(addrLayer);
});

const zoneLayer = L.layerGroup().addTo(map);
const lobeLayer = L.layerGroup().addTo(map);
const interLayer = L.layerGroup().addTo(map);

function esc(s){return String(s).replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}

function render(){
  const sid = currentSchool, mins = document.getElementById('minutes').value;
  const mode = document.getElementById('mode').value, showLobes = document.getElementById('showLobes').checked;
  zoneLayer.clearLayers(); lobeLayer.clearLayers();
  let zc = 0, lc = 0; const bounds = L.latLngBounds();

  if (sid === 'none') {  // «очистить»: зоны и лепестки убраны, метро остаётся
    document.getElementById('info').textContent = 'зон: 0, лепестков: 0';
    renderInter();
    return;
  }

  const zds = ZONES[mode] || {features: []};
  zds.features.forEach(f => {
    const p = f.properties;
    if (sid !== 'all' && p.school_id !== sid) return;
    if (mins !== 'both' && p.min != mins) return;
    const c = COLORS[p.min] || '#555';
    L.geoJSON(f, {style: {color: c, weight: 2, fillColor: c, fillOpacity: 0.18},
      onEachFeature: (ft, lyr) => lyr.bindPopup(
        `<b>${esc(p.name)}</b><br>${p.min} мин · ${MODE_LABELS[mode] || mode}<br>${esc(p.status)}`)})
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
  renderInter();
}

function renderInter(){
  interLayer.clearLayers();
  const info = document.getElementById('interInfo');
  const on = document.getElementById('interOn').checked;
  const mode = document.getElementById('mode').value;
  const mins = document.getElementById('minutes').value;
  if (!on) { info.textContent = 'отметьте ≥ 2 области и включите сценарий'; return; }
  const chosen = [...document.querySelectorAll('.ichk:checked')].map(cb => {
    const [key, sid] = cb.value.split(':');
    return {key, sid, label: cb.closest('label').querySelector('.aname').textContent,
            feats: zoneFeaturesFor(mode, key, sid, mins)};
  });
  if (chosen.length < 2) { info.textContent = `выбрано областей: ${chosen.length} — нужно ≥ 2`; return; }
  const m = mins === 'both' ? 40 : Number(mins);
  const usable = chosen.filter(c => c.feats.length > 0);
  if (usable.length < 2) {
    info.innerHTML = `<span class="empty">у выбранных областей нет зон ${m} мин (${MODE_LABELS[mode] || mode})</span>`;
    return;
  }
  // выбранные области полупрозрачным
  chosen.forEach(c => c.feats.forEach(f =>
    L.geoJSON(f, {style: {color: '#666', weight: 1, fillColor: '#888', fillOpacity: 0.06}}).addTo(interLayer)));
  // пересечение (коричневое)
  let acc = null;
  usable.forEach(c => {
    if (!acc) { acc = c.feats[0]; return; }
    acc = turf.intersect(acc, c.feats[0]);
  });
  if (!acc) { info.innerHTML = `<span class="empty">пересечение пусто (${usable.length} областей)</span>`; return; }
  L.geoJSON(acc, {style: {color: '#8b4513', weight: 2.5, fillColor: '#8b4513', fillOpacity: 0.3, dashArray: '6 3'}})
    .addTo(interLayer);
  const area = turf.area(acc) / 1e6;
  const inside = Object.entries(ADDRS)
    .filter(([aid, a]) => turf.booleanPointInPolygon([a.lon, a.lat], acc))
    .map(([aid, a]) => a.label);
  info.innerHTML = `пересечение ${usable.length} обл. (${m} мин, ${MODE_LABELS[mode] || mode}): ` +
    `<b>${area.toFixed(1)} км²</b>` +
    (inside.length ? `<br>адреса внутри: ${inside.map(esc).join(', ')}` : '');
}

function toggleAnalytics(){
  const panel = document.getElementById('analytics');
  const collapsed = panel.classList.toggle('collapsed');
  document.getElementById('anaArrow').textContent = collapsed ? '▲' : '▼';
}

document.getElementById('anaTab').addEventListener('click', toggleAnalytics);

document.getElementById('minutes').addEventListener('change', render);
document.getElementById('mode').addEventListener('change', render);
document.getElementById('showLobes').addEventListener('change', render);
document.getElementById('interOn').addEventListener('change', renderInter);
document.querySelectorAll('.ichk').forEach(cb => {
  cb.addEventListener('change', () => { updateSchoolMarkers(); renderInter(); });
});
document.getElementById('selAll').addEventListener('click', () => {
  document.querySelectorAll('.ichk').forEach(cb => cb.checked = true);
  updateSchoolMarkers(); renderInter();
});
document.getElementById('selNone').addEventListener('click', () => {
  document.querySelectorAll('.ichk').forEach(cb => cb.checked = false);
  updateSchoolMarkers(); renderInter();
});
updateSchoolMarkers();
render();
</script></body></html>
"""

html = (html.replace("__MODE_OPTIONS__", mode_options)
            .replace("__CHECKBOXES__", checkbox_html)
            .replace("__SCHOOLS__", school_json)
            .replace("__ADDRS__", addr_json)
            .replace("__BUILDINGS__", buildings_json)
            .replace("__ZONES_ADDR__", zones_addr_json)
            .replace("__ZONES__", zones_json)
            .replace("__LOBES__", lobes_json)
            .replace("__METRO__", metro_json))

dest = OUT / "zones_viewer.html"
dest.write_text(html, encoding="utf-8")
print("вьюер:", dest, f"({dest.stat().st_size//1024} КБ)")
print("школ:", len(schools), "| адресов:", len(addrs), "| корпусов:", len(buildings),
      "| режимов:", len(DATASETS),
      "| зон:", sum(len(z['features']) for z in zones.values()),
      "| зон адресов:", sum(len(z['features']) for z in zones_addr.values()),
      "| лепестков:", sum(len(l['features']) for l in lobes.values()),
      "| линий метро:", len(metro.get('features', [])))
