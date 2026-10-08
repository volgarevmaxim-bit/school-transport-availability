# api_facts.md — факты по API 2ГИС (методика v1)

Собрано 08.10.2026: Context7 (/2gis/docs-mirror, снапшот в docs_snapshot/ctx7_notes.md) + пробы
(src/probe_stage0.py, сырые ответы в data/raw/). Статусы: [подтверждено] = доки + живой ответ;
[проверено-экспериментом] = только живой ответ; [не проверено] = ни доки, ни проба; [доки-не-сходятся] = противоречие.

## Ключ и бюджет
- [проверено-экспериментом] Один ключ работает на: catalog (geocoder), routing (routing/7.0.0,
  isochrone/2.0.0, public_transport/2.0, get_dist_matrix), static.maps.2gis.com. Ключ передаётся
  параметром `key` в query.
- [проверено-экспериментом] Отдельные счётчики по сервисам проверить нельзя через API — остатки
  смотрит владелец в Platform Manager. Локальный учёт — data/db/experiments.sqlite (requests).
- [проверено-экспериментом] Кэш по sha1(запрос без ключа): повтор не тратит бюджет (проба 1).

## Изохроны (POST /isochrone/2.0.0)
- [подтверждено] Тело: start{lat,lon}, durations[], transport (driving | public_transport | walking),
  reverse (только driving), start_time (ISO), format (wkt), public_transport_types.
- [подтверждено] В UI доков reverse отключается при выборе public_transport → параметр для ОТ
  официально не предусмотрен; Стадия 3 проверит поведение сервера на reverse:true для ОТ.
- [проверено-экспериментом] driving, durations [600], reverse false, start_time DATE 05:10Z → 200,
  status "OK", isochrones[0].geometry — WKT (MULTIPOLYGON, ~3.4 КБ).
- [проверено-экспериментом] public_transport, durations [600], start_time DATE 05:30Z → 200, status
  "OK", WKT MULTIPOLYGON (~1.1 КБ). Изохроны ОТ на демо-ключе работают.
- [не проверено] Семантика start_time (выезд vs прибытие) для driving при reverse true/false —
  Стадия 2; влияние start_time для ОТ (расписание) — Стадия 3 (сравнение 05:30Z vs 20:00Z);
  допустимые значения public_transport_types — Стадия 3.

## Маршруты на авто (POST /routing/7.0.0/global) — НОВЫЙ API (v1-ТЗ предполагало get_directions)
- [подтверждено] Тело: points[{type:"stop",lon,lat}...], transport:"driving", output
  ("summary"|"detailed"), locale, utc (Unix сек), traffic_mode ("statistics"|...), filters
  (dirt_road|toll_road|ferry).
- [проверено-экспериментом] output=summary → result[0] = {duration, length}: duration в СЕКУНДАХ
  (398 с на 2.2 км в 08:10 МСК с statistics — правдоподобно для часа пик), length в МЕТРАХ (2168).
  Поля total_duration/total_distance в summary НЕТ — они из старых примеров/другого вывода.
- [проверено-экспериментом] РЕЙТ-ЛИМИТ: ~50 запросов/мин (серия 48 за 16 с → 429 «too many
  requests», блок ≥3 мин; счётчики сервисов раздельные — изохроны в это время работали).
  В client.py: пейсинг 1.3 с для routing-семейства + ретрай 429. 429, видимо, не тратят бюджет.
- [проверено-экспериментом] Статистика пробок почти плоская в окне 07:50–08:10 МСК (±20 с на
  1200 с маршрута) — гипотезы A/B в Стадии 2 этим контролем не различаются.
- [не проверено] utc — время ОТПРАВЛЕНИЯ (по названию и примеру доков; Стадия 2: данные согласны
  с A, но различие A/B в пределах шума).

## Общественный транспорт (POST /public_transport/2.0)
- [подтверждено] Тело: source{point{lat,lon}}, target{point{lat,lon}}, transport[] (ОБЯЗАТЕЛЬНО,
  иначе 400 "'source' or 'target' or 'transport' section is not found or empty"), start_time
  (Unix сек, время отправления), enable_schedule (bool), locale. Лимит: ≤4 точки? (не проверено).
- [проверено-экспериментом] Ответ = СПИСОК альтернатив (не {result:{items}}). Альтернатива:
  total_duration (сек, с ожиданием — 963 с на 2.2 км), transfer_count, crossing_count,
  total_distance, total_walkway_distance, transport (использованные виды), movements[].
  Движение (movement): type (walkway | bus/tram/...), distance, moving_duration, waiting_duration,
  routes/platforms (время прибытия/отправления рейса — Стадия 4 определит точные поля).
- [не проверено] Формула «время маршрута = от начала первого до конца последнего участка»:
  кандидат — total_duration == Σ(moving_duration + waiting_duration); проверить в Стадии 4;
  допустимые значения transport[] (bus/trolleybus/tram приняты; metro? — Стадия 3/4).

## Матрица расстояний (POST /get_dist_matrix?version=2.0)
- [подтверждено] Тело: points[{lat,lon}], sources[int], targets[int]. Синхронный режим: ≤25 в
  sources/targets, ≤2000 км между точками.
- [проверено-экспериментом] Минимальное тело → 200: routes[] = {source_id, target_id, status,
  distance (м), duration (с), reliability}. Пробок в минимальном ответе нет; параметров
  traffic_mode/utc в доках не нашёл.
- [не проверено] Поддержка пробок/времени отправления в матрице. Для измерений «с пробками в
  заданное время» основной инструмент — routing/7.0.0 (utc + traffic_mode=statistics); матрица —
  для массовых измерений без пробок. Стадия 2 решит по факту.

## Статическая карта (GET static.maps.2gis.com/2.0)
- [подтверждено] Параметры: s (размер WxH), c (центр lat,lon), z (zoom 1–18), pt (маркеры),
  ls (линии, ~c:цвет~w:ширина), pn (ПОЛИГОНЫ, ~c:цвет~f:заливка), g (geojson), key.
  ПОЛИГОНЫ ПОДДЕРЖИВАЮТСЯ нативно → Стадия 7 рисует зоны без matplotlib-подложки.
- [проверено-экспериментом] маркер+линия+полигон в одном запросе → 200, PNG (проба: 172 КБ,
  визуальная проверка — reports/plots/stage0_probe.png).
- [не проверено] Лимиты длины URL/marker-строк; формат заливки f:RRGGBBAA; приоритет g (geojson)
  для полигонов изохрон.

## Геокодер (GET catalog.api.2gis.com/3.0/items/geocode)
- [проверено-экспериментом] q + fields=items.point → result.items[0].point{lat,lon}. В основном
  не нужен: координаты школ из канона school-portal (Стадия 1). Точечные проверки — по запросу.
