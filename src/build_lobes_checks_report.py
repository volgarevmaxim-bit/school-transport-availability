"""Сводный отчёт по проверкам лепестков (lobes_checks.csv) — reports/lobes_checks_report.md.
Идемпотентен: пересобирается на каждом тике, показывает прогресс и финальные вердикты.
Запуск: .venv/Scripts/python.exe src/build_lobes_checks_report.py
"""
from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHECKS = ROOT / "data" / "out" / "lobes_checks.csv"
OUT_MD = ROOT / "reports" / "lobes_checks_report.md"

TOTAL_LOBES = 89  # 51 ОТ + 38 авто (lobes_review.md)

BAND = {
    "подтверждено": "✅",
    "частично": "🟡",
    "противоречит": "❌",
    "противоречит (caveat авто)": "❌",
    "204: маршрут не найден": "🚫",
}


def main() -> None:
    rows = list(csv.DictReader(CHECKS.read_text(encoding="utf-8-sig").splitlines()))
    done = [r for r in rows if r["status"] in ("200", "204", "400", "403", "ERR")]
    ok = [r for r in rows if r["status"] == "200"]
    errs = [r for r in rows if r["status"] != "200"]

    pt = [r for r in ok if r["mode"] == "public_transport"]
    car = [r for r in ok if r["mode"] == "driving"]

    def verdict_stats(rows_subset):
        c = Counter()
        for r in rows_subset:
            if not r["verdict"]:
                c["без вердикта"] += 1
            else:
                c[r["verdict"]] += 1
        return c

    L = [f"# Отчёт: точечные проверки гипотез лепестков (2ГИС, финальный прогон)",
         "",
         f"Проверено: {len(done)}/{TOTAL_LOBES} лепестков "
         f"(ОТ {len([r for r in done if r['mode']=='public_transport'])} из 51, "
         f"авто {len([r for r in done if r['mode']=='driving'])} из 38).",
         f"Ошибки/особые статусы: {len(errs)}.",
         "",
         "Метод: endpoint = самая дальняя точка пересечения луча (азимут stage6) с границей",
         "зоны (школа, режим, минуты); ОТ: pt-маршрут школа→endpoint 05:30Z, DATE=2026-10-14;",
         "авто: routing школа→endpoint, выезд 08:30 МСК − минуты, traffic_mode=statistics.",
         "Вердикт по ratio = duration/(min×60): ✅ ≤1.2 · 🟡 ≤1.5 · ❌ >1.5",
         "(авто ❌ — с известным caveat оптимистичности изохрон на дальних сегментах).",
         "204 = маршрут не найден (кандидат в артефакты зоны).",
         ""]

    cpt = verdict_stats(pt)
    ccar = verdict_stats(car)
    L += ["## Сводка", "",
          f"| Режим | Всего 200 | ✅ | 🟡 | ❌ | 204/без вердикта |",
          f"|---|---|---|---|---|---|",
          f"| ОТ | {len(pt)} | {cpt.get('подтверждено',0)} | {cpt.get('частично',0)} | "
          f"{cpt.get('противоречит',0)} | {cpt.get('без вердикта',0)} |",
          f"| Авто | {len(car)} | {ccar.get('подтверждено',0)} | {ccar.get('частично',0)} | "
          f"{ccar.get('противоречит (caveat авто)',0)} | {ccar.get('без вердикта',0)} |",
          ""]

    def block(title, rows_subset, cols=None):
        cols = cols or ["lobe_id", "school_name", "min", "ratio", "duration_sec", "corridors",
                        "hypothesis"]
        out = [f"## {title} ({len(rows_subset)})", "",
               "| " + " | ".join(cols) + " |", "|---" * len(cols) + "|"]
        for r in rows_subset:
            out.append("| " + " | ".join(str(r.get(c, "")).replace("|", "/")[:90] for c in cols) + " |")
        out.append("")
        return out

    bad = [r for r in pt if r["verdict"] in ("противоречит",)]
    mid = [r for r in pt if r["verdict"] == "частично"]
    good = [r for r in pt if r["verdict"] == "подтверждено"]
    bad_car = [r for r in car if r["verdict"] == "противоречит (caveat авто)"]
    mid_car = [r for r in car if r["verdict"] == "частично"]
    no_route = [r for r in ok if r["status"] == "204"]

    L += block("❌ ОТ — противоречат зоне (кандидаты на исключение из этапа цен)", bad)
    L += block("🟡 ОТ — частично (на грани допуска)", mid)
    L += block("✅ ОТ — подтверждены", good)
    L += block("🚫 Маршрут не найден (204)", no_route)
    L += block("❌ Авто — за пределами 1.5× (известный caveat изохрон)", bad_car)
    L += block("🟡 Авто — частично", mid_car)

    L += ["## Гипотезы против проверок (топ-10 таблицы lobes_review)", ""]
    top = sorted([r for r in rows], key=lambda r: (r["table_order"] == "", int(r["table_order"]) if r["table_order"] else 10**9))[:10]
    for r in top:
        band = BAND.get(r["verdict"], "·")
        L.append(f"- {band} **{r['lobe_id']}** {r['mode']} {r['min']} мин: "
                 f"гипотеза «{r['hypothesis'][:120]}» → api {r['duration_sec']} с "
                 f"(ratio {r['ratio']}), коридоры: {r['corridors'] or '—'}")

    OUT_MD.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"Отчёт: {OUT_MD} ({len(done)}/{TOTAL_LOBES} проверено)")


if __name__ == "__main__":
    main()
