# log.md — журнал эксперимента (методика v1)

## Стадия 0. Окружение и «всё работает» — 08.10.2026

Отклонения от плана (сразу в первую строку):
1. v1-ТЗ предполагало get_directions — по докам актуален НОВЫЙ POST /routing/7.0.0/global
   (utc в Unix + traffic_mode=statistics); поля summary — duration[сек]/length[м], НЕ total_duration.
2. public_transport/2.0 требует НЕпустой transport[] (иначе 400); ответ — СПИСОК альтернатив
   (не {result:{items}}), ключевое поле total_duration.
3. static.maps.2gis.com/2.0 поддерживает полигоны нативно (pn) — Стадия 7 без matplotlib.
4. Старый пример запроса geocode (проверка ключа) сохранён в ином формате и в кэш не попал —
   +1 лишний geocoder-запрос (итого за стадию 8 новых + 1 = 9 ≤ 10).

Запущено: venv (py3.11, requests/shapely/pyyaml), каркас папок, src/client.py (кэш sha1 без ключа,
бюджет/резерв по сервисам, sqlite-журнал, msk_to_utc/msk_to_unix), снапшот канона
(data/upstream/entities_20261008_d63ba54.json, md5 7135ec2c...), Context7 /2gis/docs-mirror
(6 вопросов, по ≤3 на тему), api_facts.md, пробы probe_stage0.py.

Расход (новых, за стадию): geocoder 1, isochrone 2, routing 1, public_transport 2,
distance_matrix 1, static_maps 1. Остатки: geocoder 998, routing 999, pt 998, matrix 999,
isochrone 998, static 999 (лимит 1000, резерв 100; счётчик Platform Manager — у владельца).

Ключевые цифры: HTTP 200 на всех 6 сервисах; кэш: повтор geocode — 0 бюджет; driving-изохрона
600с → WKT 3.4 КБ; ОТ-изохрона 600с → WKT 1.1 КБ; routing7 ЛИТ→Л2Ш 08:10 МСК statistics =
398 с / 2168 м; ОТ ЛИТ→Л2Ш 08:30 = total_duration 963 с (0 пересадок); matrix ЛИТ→{Л2Ш,1514} =
426 с / 1401 с; static PNG (маркер+линия+полигон) — визуально подтверждено.

ГЕЙТ 0: ПРОЙДЕН. Ключ валиден на всех сервисах, кэш работает, api_facts.md заполнен
(непроверенное помечено), upstream-снапшот есть.

Следующий шаг: Стадия 1 — черновик списка готов (config/schools.csv, selected=20: Л2Ш + 11 ЮЗАО
+ 8 ЗАО); ждём подтверждения владельца (ГЕЙТ 1).

## Стадия 1. Школы — черновик 08.10.2026

- Источник: канон school-portal (snapshot @d63ba54). Геокодирование не требовалось (0 запросов).
- config/schools.csv: 79 blue/red school-сущностей; selected=20 (verified 9, stub 11; blue 16,
  red 4; Л2Ш + 11 ЮЗАО + 8 ЗАО). Сомнительных координат не выявлено (все точки канона с coords).
- ГЕЙТ 1: ОТКРЫТ — ждём подтверждения/правок владельца.
