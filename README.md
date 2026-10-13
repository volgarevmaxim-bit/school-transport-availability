# school-transport — транспортная доступность школ Москвы (проект №23)

Единая точка входа в проект. Для продолжения сессии достаточно этого файла + HANDOFF.md.

## Зачем проект и куда движется

Цель (ТЗ v2 в docs/): изохроны 20/40 мин (авто + общественный транспорт, прибытие к 8:30)
для ~20 школ ЮЗАО/ЗАО → выявить «лепестки» аномальной доступности → статические карты →
следующий этап: сопоставление лепестков с ценами на квартиры («где жить, чтобы быстро
добираться до выбранной школы»).

Статус (13.10): стадии 0–7 готовы. Гейты 0–3 пройдены, стадии 2 и 7 закрыты 13.10.
Вьюер live. Ждёт: решение владельца по caveat авто-зон и «го» на этап цен.

## Как устроено

Конвейер стадий по ТЗ:
1. Выборка школ (config/schools.csv, 20 selected из канона).
2. Семантика reverse-изохрон авто (start_time). Гипотеза A принята (utc = отправление);
   caveat: reverse-изохрона оптимистична против routing — ~14% на ближних сегментах,
   до ~2× на дальних.
3. Reverse для ОТ: сервер игнорирует (IoU=1.0) — зоны ОТ строятся «от школы».
4. Ошибка направления ОТ: измерение T_in/T_out, зоны занижены по времени, не по направлению.
5. Зоны-изохроны: data/out/{car,pt}_zones.geojson (20/25/30/35/40 мин).
6. Лепестки: радиальные профили r(θ) по 5°, порог медиана+k·MAD → lobes_{car,pt}.csv/geojson.
7. Статические карты 2ГИС (40 PNG: 38 фреймов зон+нумерованных лепестков + 2 обзора) +
   обзор лепестков (reports/lobes_review.md, 89 лепестков с гипотезами).

- Источник школ — канон №22 schools-map-mathex (data/entities.json); снапшоты в data/upstream/.
- Данные — 2ГИС API (ключ в winreg), кэш sha1 в data/raw/, журнал sqlite
  data/db/experiments.sqlite (probes/verdicts), счётчики лимитов в src/client.py.
- Вьюер — статический HTML+Leaflet (всё вшито в index.html); публикация на gh-pages через
  src/publish_pages.py (идемпотентно: пересборка + пуш ветки gh-pages).
- Кросс-задачи с каноном (адреса школ, замены баз, чистка) завершены 10–12.10 — детали
  в reports/log.md и истории №22.

## Стек и правила кодинга

- Python 3.11 в .venv; запускать `.venv/Scripts/python.exe`. Библиотеки: requests, shapely, pyyaml.
- Скрипты идемпотентные/возобновляемые (по CSV/кэшу), НЕ дублируют запросы при повторе.
- Пейсинг 2ГИС: routing/pt 3.0с (per-minute окно ~25 на routing-семейство: routing+pt ОБЩЕЕ);
  429 → стоп на день без повторов (правило владельца).
- Конвенция азимутов stage6: 0°=восток, плоскость lon/lat (в lobes_*.csv и stage7_frames.csv).
  Компасный бэринг = (90°−az) mod 360. ВСЕ направления проверять этой формулой.
- CSV: читать/писать utf-8-sig (BOM). lat/lon в csv_rows канона — строки.
- /tmp MSYS ≠ /tmp Windows-python: обмен файлами — через явные C:\-пути.
- Публикация: commit/push main → src/publish_pages.py → проверка live с cache-busting +
  сверка содержимого gh-pages через GitHub API contents (Raw может отдавать прокси-кэш).

## Папки

- `config/` — schools.csv (20 выбранных), experiment.yaml (DATE=2026-10-14 и пр.),
  buildings.csv (корпуса для вьюера).
- `src/` — stageN_*.py по стадиям; client.py (2ГИС: кэш, счётчики, пейсинг);
  build_viewer.py + publish_pages.py (вьюер → gh-pages); build_lobes_review.py (отчёт
  по лепесткам); check_frame_geometry.py + vision_batch_review.py + vision_quality_check.py
  (пиксельный обзор карт); build_review_batches.py + merge_vision_reviews.py (конвейер обзора).
- `data/upstream/` — снапшоты канона + UPSTREAM.md (коммит, md5). Брать свежий по
  max(glob), НЕ next(glob).
- `data/raw/` — кэш ответов 2ГИС (sha1).
- `data/out/` — зоны/лепестки (geojson/csv), stage2_recheck.csv и пр.
- `data/db/` — experiments.sqlite.
- `reports/` — log.md (журнал всех стадий), api_facts.md (грабли 2ГИС), lobes_review.md
  (89 лепестков, топ-10, дальние ОТ), gate7_report.md (итог владельцу), plots/stage7/
  (карты + stage7_frames.csv + geometry_check.json + vision_raw/ + review_batches/ +
  reviews_*.json).
- `docs/` — ТЗ v2.

## Как продолжать сессию (порядок чтения)

1. README.md — этот файл.
2. HANDOFF.md — состояние последней сессии, счётчики 2ГИС, следующий шаг, свежие грабли.
3. Детали по необходимости: reports/log.md (история стадий), reports/api_facts.md
   (грабли API), reports/lobes_review.md (лепестки), скилл schools-map-mathex-ops
   (ops-инструкции, vision-фолбэк, конвенция азимутов).
4. INDEX (Hermes_Project_INDEX.md) — только чтобы найти проект; вся детальность здесь.

## Ключевые грабли

- Лимиты 2ГИС: routing_api 50/день ОБЩИЙ (маршруты+ОТ) + per-minute ~25/мин;
  isochrone/static/matrix/geocoder по 50/день; reserve 5. Сброс 03:00 МСК.
- reverse driving-изохрона направленно-оптимистична vs routing/statistics: ~14% на
  ближних сегментах, до ~2× на дальних (азимутальная выборка 13.10).
- vision_analyze может быть не сконфигурирован → прямой вызов bothub
  (deepseek-v4-flash-vision-exp, ключ в env-файле ~/.hermes) — см. скилл.
- Активный конфиг Hermes: AppData\Local\hermes\config.yaml (не ~/.hermes — старый).
- Снапшот канона: max(glob) по имени файла, иначе возьмётся СТАРЫЙ.
