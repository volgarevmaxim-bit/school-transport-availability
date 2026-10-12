import csv
import json
import math
import sqlite3
import sys
import io
from datetime import datetime, timezone

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

print("=== 1) ТЕЛО 429-ОТВЕТА (последний) ===")
import glob, os
raws = sorted(glob.glob('data/raw/routing/*.json'), key=os.path.getmtime)
for f in raws:
    m = json.load(open(f, encoding='utf-8'))
    if m.get('status') == 429:
        print(f, '| utc:', m.get('utc_time'))
        print('  request:', m.get('request_no_key', '')[:150])
        r = m.get('response')
        if isinstance(r, dict):
            print('  body:', json.dumps(r, ensure_ascii=False)[:400])
        else:
            print('  body:', str(r)[:400])

print("\n=== 2) СЕГОДНЯШНИЕ routing-запросы: тайминги ===")
con = sqlite3.connect('data/db/experiments.sqlite')
rows = con.execute("SELECT utc_time, status, cached FROM requests WHERE service='routing' AND utc_time LIKE '2026-10-12%' ORDER BY id").fetchall()
print('всего сегодня:', len(rows))
for i, (ut, st, c) in enumerate(rows[:3]):
    print(' ', i, ut, st, 'cached' if c else 'live')
print('  ...')
for i, (ut, st, c) in enumerate(rows[-4:], len(rows) - 4):
    print(' ', i, ut, st, 'cached' if c else 'live')
t0 = datetime.fromisoformat(rows[0][0])
tlast = datetime.fromisoformat(rows[-1][0])
print(f'первый {t0.isoformat()}, последний {tlast.isoformat()}, span {(tlast-t0).total_seconds():.0f}с, rate {(len(rows)-1)/((tlast-t0).total_seconds()/60):.1f}/мин')

print("\n=== 3) ТОЧКИ ВЫБОРКИ: расстояния от школы ===")
def hav(lat1, lon1, lat2, lon2):
    R = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2 * R * math.asin(math.sqrt(a))

schools = {
    'лицей-вторая-школа-в-ф-овчинникова': (55.69799, 37.55644),
    'школа-2007-фмш': (55.533064, 37.533619),
}
with open('data/out/stage2_recheck.csv', encoding='utf-8-sig') as f:
    for r in csv.DictReader(f):
        lat0, lon0 = schools[r['school_id']]
        d = hav(lat0, lon0, float(r['lat']), float(r['lon'])) / 1000
        print(f"{r['school_id'][:28]:30s} az={r['azimuth']:>3}  dist={d:5.1f} км  tA={r.get('tA')} tB={r.get('tB')}")

print("\n=== 4) СТРУКТУРА P_rev (MultiPolygon): части и площади ===")
from shapely import wkt as shapely_wkt
for f in ['data/raw/isochrone/59d96ebf91b593e25c256161904366dc6b79fa2b.json',
          'data/raw/isochrone/95a093ce5ada84d88b20ce0013e9871c39321de0.json']:
    m = json.load(open(f, encoding='utf-8'))
    g = shapely_wkt.loads(m['response']['isochrones'][0]['geometry'])
    print(os.path.basename(f)[:10], 'type', g.geom_type)
    if g.geom_type == 'MultiPolygon':
        areas = [p.area for p in g.geoms]
        areas.sort(reverse=True)
        print('  частей:', len(areas), '| площади (км², убыв):', [round(a*111.32*111.32*math.cos(math.radians(55.65)), 2) for a in areas[:12]])
    else:
        print('  единый полигон, площадь', round(g.area*111.32*111.32*math.cos(math.radians(55.65)), 2), 'км²')
