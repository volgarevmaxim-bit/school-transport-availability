"""Сборка reports/lobes_review.md: гипотезы суб-агентов (deleg_43325ab8) + метрики лепестков.

Вход: data/out/lobes_car.csv, lobes_pt.csv, ot_only_lobes.csv; reviews-файлы
reports/plots/stage7/reviews_*.json (массив {reviews:[...]} от суб-агентов — положить
вручную по результатам делегирования). Выход: reports/lobes_review.md (таблица,
сортировка: сначала «только у ОТ» (кандидаты дешёвых районов), затем score).
score = zone_share * elongation (доля зоны × вытянутость) — вес для этапа цен.
"""
import csv
import json
import sys
import io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
ROOT = Path(__file__).resolve().parent.parent
REVIEWS_DIR = ROOT / "reports" / "plots" / "stage7"
OUT = ROOT / "reports" / "lobes_review.md"

SCHOOLS = {}
with open(ROOT / "config" / "schools.csv", encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        SCHOOLS[r["entity_id"]] = r["name"]

lobes = {}  # lobe_id -> метрики
for mode, fn in (("car", "lobes_car.csv"), ("pt", "lobes_pt.csv")):
    with open(ROOT / "data" / "out" / fn, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            lobes[r["lobe_id"]] = {**r, "mode_label": mode}

ot_only = set()
if (ROOT / "data" / "out" / "ot_only_lobes.csv").exists():
    with open(ROOT / "data" / "out" / "ot_only_lobes.csv", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            ot_only.add(r["lobe_id"])

reviews = []
for f in sorted(REVIEWS_DIR.glob("reviews_*.json")):
    data = json.loads(f.read_text(encoding="utf-8"))
    items = data.get("reviews", [])
    reviews.extend(items)
print(f"гипотез от суб-агентов: {len(reviews)}")

rev_by_id = {r["lobe_id"]: r for r in reviews}
missing = [lid for lid in lobes if lid not in rev_by_id]
print(f"лепестков без гипотезы: {len(missing)} — {missing[:8]}")

rows = []
for lid, m in lobes.items():
    rv = rev_by_id.get(lid, {})
    score = float(m["zone_share"]) * float(m["elongation"])
    rows.append({
        "lobe_id": lid,
        "school": SCHOOLS.get(m["school_id"], m["school_id"]),
        "mode": "авто" if m["mode_label"] == "car" else "ОТ",
        "min": m["min"],
        "azimuth": m["azimuth"],
        "r_km": m["r_max_km"],
        "elongation": m["elongation"],
        "zone_share": m["zone_share"],
        "ot_only": lid in ot_only,
        "confidence": rv.get("confidence", "?"),
        "direction": rv.get("direction_ru", ""),
        "hypothesis": rv.get("hypothesis_ru", ""),
        "what_seen": rv.get("what_seen_ru", ""),
        "check": rv.get("check_hint", ""),
        "score": score,
    })

rows.sort(key=lambda r: (-int(r["ot_only"]), -r["score"]))

conf_w = {"высокая": 3, "средняя": 2, "низкая": 1, "?": 0}
lines = [
    "# lobes_review.md — обзор лепестков доступности (Стадия 7, финиш)",
    "",
    f"Фреймы: reports/plots/stage7/ (38 карт школа×режим + 2 обзора), манифест stage7_frames.csv.",
    f"Всего лепестков: {len(lobes)} (авто {sum(1 for m in lobes.values() if m['mode_label']=='car')}, "
    f"ОТ {sum(1 for m in lobes.values() if m['mode_label']=='pt')}); гипотез собрано: {len(reviews)}.",
    "⚠️ ВНИМАНИЕ: визуальный бэкенд (vision-анализ) был недоступен 12.10 (404) — ВСЕ гипотезы",
    "в этой таблице ДЕДУКТИВНЫЕ: азимут + дальность + координаты школы + знание сети дорог/метро",
    "Москвы. Часть кадров проверена визуально в ранней части сессии (Л2Ш car/pt, 2007 pt, 1580,",
    "школа-109 — маркеры и направления сходятся с азимутами). Полный пиксельный обзор 38 кадров —",
    "перенесён на следующую сессию (повторный прогон vision, без API-запросов). Уверенность",
    "«высокая» ниже означает «гипотеза почти однозначна по геометрии», НЕ «визуально подтверждена».",
    "Порядок таблицы — приоритет для этапа цен: сначала «только у ОТ» (кандидаты «дешёвый район —",
    "быстрый доступ», авто-аналога в том же секторе нет), внутри — по score = доля зоны × вытянутость.",
    "Уверенность: высокая (на карте видна конкретная магистраль/линия), средняя (вероятно, нужна",
    "проверка), низкая (не видно — чистая гипотеза).",
    "",
    "| # | Лепесток | Школа | Режим | Мин | Аз° | r,км | Выт | Доля | Увер. | Направление | Гипотеза | Чем проверить |",
    "|---|----------|-------|-------|-----|-----|------|-----|------|-------|-------------|----------|---------------|",
]
for i, r in enumerate(rows, 1):
    tag = " 🚇" if r["ot_only"] else ""
    lines.append(
        f"| {i} | `{r['lobe_id']}`{tag} | {r['school']} | {r['mode']} | {r['min']} | {r['azimuth']} | "
        f"{r['r_km']} | {r['elongation']} | {r['zone_share']} | {r['confidence']} | {r['direction']} | "
        f"{r['hypothesis']} | {r['check']} |"
    )

# r_max_km для секции дальних
lines_extra = ["", "## Дальние лепестки ОТ (r ≥ 15 км) — «быстрый дальний доступ»", "",
               "| Лепесток | Школа | Мин | Аз° | r,км | Увер. | Гипотеза |",
               "|---|-------|-----|-----|------|-------|----------|"]
far = [r for r in rows if r["mode"] == "ОТ" and float(r["r_km"]) >= 15.0]
far.sort(key=lambda r: -float(r["r_km"]))
for r in far:
    lines_extra.append(f"| `{r['lobe_id']}` | {r['school']} | {r['min']} | {r['azimuth']} | "
                       f"{r['r_km']} | {r['confidence']} | {r['hypothesis']} |")
lines += lines_extra
lines += [
    "",
    "## Сводка по уверенности",
    "",
]
for lvl in ("высокая", "средняя", "низкая", "?"):
    n = sum(1 for r in rows if r["confidence"] == lvl)
    lines.append(f"- {lvl}: {n}")

lines += [
    "",
    "## Топ-10 для владельца (по приоритету)",
    "",
]
for i, r in enumerate(rows[:10], 1):
    lines.append(f"{i}. **{r['school']}** ({r['mode']}, {r['min']} мин, аз. {r['azimuth']}°, {r['r_km']} км): "
                 f"{r['hypothesis']} ({r['confidence']}). {r['check']}")

OUT.write_text("\n".join(lines), encoding="utf-8")
print(f"написано: {OUT} ({len(rows)} строк)")
