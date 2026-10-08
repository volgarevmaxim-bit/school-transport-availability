# HANDOFF — Транспортная доступность школ Москвы (проект №23)

Состояние на конец сессии 08.10.2026 (CLI-сессия).

## LIVE

- Вьюер (GitHub Pages): https://volgarevmaxim-bit.github.io/school-transport-availability/
  Поиск школы по набору текста («втор» → Лицей «Вторая школа»), селекторы время (20/40/обе) и
  режим, чекбокс лепестков, попапы с метриками. Данные встроены в index.html.
  Публикация: src/publish_pages.py (идемпотентно: пересборка вьюера → пуш ветки gh-pages).
  Кэш Pages ~1 мин; зависший build (building > 2 мин) лечится ПУСТЫМ КОММИТОМ в gh-pages,
  НЕ POST /pages/builds. Pages включены владельцем (токен не имеет прав на Pages API — 403).
- Репо: volgarevmaxim-bit/school-transport-availability (main + gh-pages).

## СОСТОЯНИЕ СТАДИЙ (порядок перестроен владельцем 08.10: зоны/лепестки сначала, проверки потом)

- ГЕЙТ 0 ✓: ключ валиден (6 сервисов), кэш, api_facts.md, снапшот канона @d63ba54.
- ГЕЙТ 1 ✓: 20 школ (Л2Ш + 11 ЮЗАО + 8 ЗАО), config/schools.csv.
- ГЕЙТ 2 ✓: авто — гипотеза A (start_time = выезд); зоны помечаются «приближение, +8–14%».
- ГЕЙТ 3 ✓: reverse ОТ игнорируется; mcc/mcd не работают; расписание на зону влияет.
- Стадия 5 ОТ ✓: data/out/pt_zones.geojson (40 полигонов, 20/40 мин, старт 05:30Z).
- Стадия 6 ОТ ✓: 45 лепестков (data/out/lobes_pt.csv, lobes_pt.geojson, profiles_pt/*.png).
  Лучи: школа-109 40-мин r=24.2 км (аз 193°), Бауманская-1580 20.2 км (аз 158°), 1158 18.6 км.
- Стадии 2/4 (проверки границ) — ПЕРЕНОСЫ по дням; Стадия 4 урезана (T_in-only 45, контроль
  T_out 20 отдельным днём). Матрицу (свой счётчик) — проверить пробой перед Стадией 2.

## ЛИМИТЫ 2ГИС (главное ограничение проекта)

- Routing API 50/день: маршруты + ОТ делят ОДИН счётчик (подтверждено Platform Manager).
- Изохроны/матрица/геокодер/static — отдельные счётчики, 50/день (для iso/matrix —
  предположение, запас обязателен). Сброс по UTC-суткам.
- client.py: daily_limits в config/experiment.yaml; стоп ЗАРАНЕЕ (лимит−резерв 5);
  429 → ответ сохранён, стоп БЕЗ повторов; пейсинг routing-семейства 1.5 с; кэш только для 200.
- Итог дня 08.10: routing_api 50/50 (исчерпан), isochrone 35/50, matrix 1, geocoder 1, static 1.

## КЛЮЧЕВЫЕ API-ФАКТЫ (reports/api_facts.md)

- Авто: POST /routing/7.0.0/global (utc Unix, traffic_mode=statistics; summary → duration[с]/length[м]).
- ОТ: POST /public_transport/2.0 (transport[] ОБЯЗАТЕЛЕН; принимает ли metro — НЕ проверено;
  ответ = список альтернатив, поле total_duration).
- Изохроны: POST /isochrone/2.0.0. driving: reverse:true работает и чувствителен к start_time;
  ОТ: reverse игнорируется; public_transport_types знает только metro (bus/tram → «все типы»).
- Матрица: POST /get_dist_matrix?version=2.0, routes[].duration (пробки/время не подтверждены).
- Static: GET static.maps.2gis.com/2.0 — полигоны pn, маркеры pt, линии ls, ключ в query.

## ЗАВТРА 09.10 — С ЧЕГО НАЧНЁМ

1. «го» → написать и запустить src/stage5_car_zones.py: 20 школ × {20-мин 05:10Z, 40-мин
   04:50Z}, driving reverse:true → data/out/car_zones.geojson. 40 изохрон ≤ 45 (резерв 5).
2. Прогнать src/stage6_lobes.py по car_zones → lobes_car.csv/geojson. Сравнить с ОТ:
   лепестки «только у ОТ» = кандидаты «дешёвый район — быстрый доступ» (гипотеза владельца).
3. build_viewer.py: добавить car в DATASETS → пересборка → publish_pages.py → проверить live.
4. Переписать src/stage4_direction_error.py под T_in-only: 3 школы × 15 точек, только T_in
   (школа→точка НЕ меряем), метрика = T_in vs порог зоны (1200/2400). 45 pt ровно в суточный
   лимит routing_api (50−5). metro включаем сразу в список — если 400, это и есть ответ
   (пробу не тратим отдельно).
5. Послезавтра (10.10): T_out-контроль (10 точек, 20 pt) + Стадия 7 (static maps) +
   матричная проба для Стадии 2.

## ГРАБЛИ

- Лимиты 2ГИС СУТОЧНЫЕ, не «1000/сервис»; серии не жечь; ошибочные ответы из кэша не
  переиспользовать (починено в client.py).
- 2GIS_API_KEY начинается с цифры → bash не видит; client.py читает winreg (User).
- entities.json канона: активный клон C:\Users\volga\schools-map-mathex (main впереди origin
  на 5 коммитов); schools-map-work отстаёт — не использовать.
- DATE = 2026-10-14 (ср). Учебные окна: 12–23.10, 05–13.11 (обе системы каникул).
- Pages: застрявший build → пустой коммит в gh-pages; CDN HTML обновляется ~1 мин после built.
