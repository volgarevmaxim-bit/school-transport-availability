# docs_snapshot: выдержки из документации (Context7, /2gis/docs-mirror, 08.10.2026)

Зеркало может отставать от живого API — расхождения проверяются экспериментом (см. api_facts.md).

## Isochrone (docs/api/navigation/isochrone/)
- POST https://routing.api.2gis.com/isochrone/2.0.0?key=... ; JSON: start{lat,lon}, durations[],
  reverse, transport (driving|public_transport|walking), format, start_time, public_transport_types.
- Пример доков (driving): durations [600,1200], reverse false, format wkt, start_time — MapGL-пример.
- В интерактивном примере: при transport=public_transport селектор reverse БЛОКИРУЕТСЯ (disabled);
  появляется группа publicTransportTypes. Т.е. reverse — только driving (по докам).
- Ответ: isochrones[0].geometry — WKT, MULTIPOLYGON (для ОТ — несколько групп полигонов).

## Routing driving (docs/api/navigation/routing/)
- НОВЫЙ API: POST /routing/7.0.0/global?key=... ; points[{type:"stop",lon,lat}...], transport:
  "driving", output ("summary"|"detailed"), locale, utc (Unix сек), traffic_mode ("statistics" —
  пример: алгоритм «без учёта пробок» в поле result[].algorithm при statistics — поле алгоритма
  относится к геометрии, время — с учётом статистики; ПРОВЕРИТЬ), filters (dirt_road|toll_road|ferry).
- Пример: traffic_mode=statistics + utc=Unix → result[] с begin/end_pedestrian_path, geometry.
- Старый get_directions в доках не встретился в текущем зеркале (v1-ТЗ ссылалось на него).

## Public transport routing (docs/api/navigation/routing/)
- POST https://routing.api.2gis.com/public_transport/2.0?key=... ; source{point{lat,lon}},
  target{point{lat,lon}}, transport[] (обязателен), start_time (Unix), enable_schedule, locale.
- enable_schedule=false → не учитывается ожидание; start_time — время отправления.

## Distance Matrix (docs/api/navigation/distance-matrix/)
- POST https://routing.api.2gis.com/get_dist_matrix?key=...&version=2.0 ;
  points[{lat,lon}], sources[], targets[]. Синхронно: ≤25/сторона, ≤2000 км.
- Пример для ОТ: transport:"public_transport" + public_transport_params{transport[], enable_schedule}
  + start_time ISO — т.е. матрица поддерживает и ОТ (для нашего проекта не требуется).

## Static maps (docs/maps/others/static/)
- GET https://static.maps.2gis.com/2.0?s={WxH}&c={lat,lon}&z={1..18}&pt={маркеры}&ls={линии}
  &pn={ПОЛИГОНЫ}&g={geojson}&key=...
- pn: lat,lon,...~c:{цвет контура}~f:{заливка, RRGGBBAA} — полигоны поддерживаются нативно.
- pt-маркеры: ~k:{тип}~c:{цвет}~n:{номер подписи}; ls: ~c:{цвет}~w:{ширина}.
- Ответ — PNG; ошибки возвращаются в теле (проверить формат при ошибке).

## Геокодер (docs/api/catalog/)
- GET catalog.api.2gis.com/3.0/items/geocode?q=...&fields=...&key=... (для точечных проверок).
