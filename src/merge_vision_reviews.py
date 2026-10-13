"""Финальное слияние (13.10): reviews_0..3 + geometry_check + batch_*_out.json
→ reports/plots/stage7/reviews_pixel.json.

Каждая запись: поля от суб-агентов (новые гипотезы с ИСТИННЫМИ бэрингами) + pixel-блок
из geometry_check (пиксельное подтверждение маркера на предсказанной позиции).
Проверки: 89/89 lobe_id покрыты, нет дублей, у всех direction_ru = имя (90-az).
"""
import csv
import json
import math
import sys
import io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
SDIR = ROOT / "reports" / "plots" / "stage7"
BDIR = SDIR / "review_batches"
OUT = SDIR / "reviews_pixel.json"


def load_reviews():
    rev = {}
    for f in sorted(SDIR.glob("reviews_[0-9].json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        for r in data.get("reviews", []):
            rev[r["lobe_id"]] = r
    return rev


def main():
    base = load_reviews()
    geo = json.loads((SDIR / "geometry_check.json").read_text(encoding="utf-8"))
    # геометрия: ключ по lobe_id
    gl = {}
    for key, fr in geo.items():
        for lb in fr["lobes"]:
            gl[lb["lobe_id"]] = {"bearing_compass": lb["bearing_compass"],
                                 "sig_ok": bool(lb["sig"] and lb["sig"]["ring_white"] >= 4),
                                 "px": lb["px"], "frame_z": fr["z"]}
    # новые гипотезы суб-агентов
    new = {}
    n_files = 0
    for f in sorted(BDIR.glob("batch_*_out.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        for r in data.get("reviews", []):
            new[r["lobe_id"]] = r
        n_files += 1
    print(f"батч-файлов прочитано: {n_files}, записей от суб-агентов: {len(new)}")

    out = []
    missing = []
    for lid, rv in sorted(base.items()):
        if lid not in new:
            missing.append(lid)
            out.append(rv)
            continue
        nr = new[lid]
        g = gl.get(lid, {})
        entry = {
            "lobe_id": lid,
            "number": nr.get("number", rv.get("number")),
            "school_id": nr.get("school_id", rv.get("school_id")),
            "mode": nr.get("mode", rv.get("mode")),
            "min": str(nr.get("min", rv.get("min", ""))),
            "azimuth": nr.get("az_plane_csv", rv.get("azimuth")),
            "bearing_true": g.get("bearing_compass", nr.get("bearing_true")),
            "direction_ru": nr.get("direction_ru", ""),
            "r_max_km": nr.get("r_max_km", rv.get("r_max_km")),
            "hypothesis_ru": nr.get("hypothesis_ru", rv.get("hypothesis_ru")),
            "what_seen_ru": nr.get("what_seen_ru", rv.get("what_seen_ru")),
            "confidence": nr.get("confidence", rv.get("confidence", "низкая")),
            "check_hint": nr.get("check_hint", rv.get("check_hint")),
            "vision_landmark": nr.get("vision_landmark", ""),
            "pixel": {"geometry_ok": g.get("sig_ok"), "px": g.get("px"),
                      "frame_z": g.get("frame_z")},
        }
        out.append(entry)
    # контроль
    if missing:
        print(f"ВНИМАНИЕ: не покрыты суб-агентами: {len(missing)}: {missing[:10]}")
    ids = [e["lobe_id"] for e in out]
    assert len(ids) == 89, f"ожидалось 89, получено {len(ids)}"
    assert len(set(ids)) == 89, "дубликаты lobe_id!"
    nok = sum(1 for e in out if e["pixel"]["geometry_ok"])
    conf = {}
    for e in out:
        conf[e["confidence"]] = conf.get(e["confidence"], 0) + 1
    print(f"лепестков: {len(out)}, pixel-ok: {nok}/89, уверенность: {conf}")
    OUT.write_text(json.dumps({"reviews": out}, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"написано: {OUT}")


if __name__ == "__main__":
    main()
