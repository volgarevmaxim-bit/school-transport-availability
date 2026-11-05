"""Точечные проверки check_hint 89 лепестков (51 ОТ + 38 авто) — финальный прогон 2ГИС
перед деактивацией ключа 06.11.2026 21:00 UTC. План: docs/PLAN_lobes_checks.md.

Идемпотентный резюм: data/out/lobes_checks.csv (ключ lobe_id). Статусы 200 и 4xx —
терминальные (скип), 'ERR' — ретрай в следующий запуск. Суточный стоп клиента
(QuotaExhaustedError) → частичное сохранение + exit 0. 429 → стоп без повторов.

Запуск: .venv/Scripts/python.exe src/check_lobes_hypotheses.py [--limit N]
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import client  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT_CSV = ROOT / "data" / "out" / "lobes_checks.csv"
REVIEW_MD = ROOT / "reports" / "lobes_review.md"
CONFIG_PATH = ROOT / "config" / "experiment.yaml"

CSV_COLS = [
    "table_order", "lobe_id", "school_id", "school_name", "mode", "min",
    "azimuth_csv", "compass_az", "r_km", "endpoint_lat", "endpoint_lon",
    "status", "duration_sec", "ratio", "transfer_count", "transports",
    "corridors", "verdict", "note", "hypothesis", "check_hint", "confidence",
]


def load_config() -> dict:
    import yaml
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


def load_schools() -> dict:
    rows = list(csv.DictReader((ROOT / "config" / "schools.csv").read_text(
        encoding="utf-8-sig").splitlines()))
    return {r["entity_id"]: r for r in rows}


def load_lobes() -> list[dict]:
    lobes = []
    for fname, mode in (("lobes_pt.csv", "public_transport"), ("lobes_car.csv", "driving")):
        rows = list(csv.DictReader((ROOT / "data" / "out" / fname).read_text(
            encoding="utf-8-sig").splitlines()))
        for r in rows:
            if r.get("suspicious", "") == "1":
                continue
            lobes.append({**r, "mode_api": mode})
    return lobes


def load_review_meta() -> dict:
    """lobe_id -> {table_order, compass_az, hypothesis, check_hint, confidence, school_name}."""
    meta = {}
    text = REVIEW_MD.read_text(encoding="utf-8")
    order = 0
    for line in text.splitlines():
        if not line.startswith("|") or "Лепесток" in line:
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 13:
            continue
        m = re.search(r"`([^`]+)`", cells[1])
        if not m:
            continue
        order += 1
        lobe_id = m.group(1)
        try:
            compass = float(re.sub(r"[^\d.]", "", cells[5]))
        except ValueError:
            compass = ""
        meta[lobe_id] = {
            "table_order": order,
            "school_name": cells[2],
            "mode_label": cells[3],
            "min": cells[4].strip(),
            "compass_az": compass,
            "confidence": cells[9],
            "hypothesis": cells[12],
            "check_hint": cells[13] if len(cells) > 13 else "",
        }
    return meta


def endpoint(lat: float, lon: float, az_deg: float, r_km: float) -> tuple[float, float]:
    """Фолбэк: луч в конвенции stage6 (0°=восток, +y=север, ПЛОСКАЯ геометрия, KMX=111.32
    для обоих направлений — как в stage6_lobes.radial_profile)."""
    az = math.radians(float(az_deg))
    dlat = r_km * math.sin(az) / 111.32
    dlon = r_km * math.cos(az) / 111.32
    return lat + dlat, lon + dlon


def lobe_tip(zones: dict, school_id: str, mode: str, min_min: int,
             lat: float, lon: float, az_deg: float, r_km: float) -> tuple[float, float]:
    """Точная вершина лепестка: самая дальняя точка пересечения луча (азимут stage6) с
    границей зоны (school_id, mode, min). Зоны многосвязные — берём максимум по всем
    пересечениям (как stage6_lobes.radial_profile). Фолбэк — плоская формула."""
    from shapely.geometry import Point, LineString
    feat = zones.get((school_id, mode, min_min))
    if feat is not None:
        spt = Point(lon, lat)
        rad = math.radians(float(az_deg))
        end = Point(spt.x + 0.6 * math.cos(rad), spt.y + 0.6 * math.sin(rad))
        inter = feat.boundary.intersection(LineString([spt, end]))
        if not inter.is_empty:
            pts = [inter] if inter.geom_type == "Point" else list(inter.geoms)
            best_p = max(pts, key=lambda p: spt.distance(p))
            return best_p.y, best_p.x
    return endpoint(lat, lon, az_deg, r_km)


def load_zones() -> dict:
    """{(school_id, mode, min): shapely polygon} из data/out/{pt,car}_zones.geojson."""
    from shapely.geometry import shape
    zones = {}
    for fname, mode in (("pt_zones.geojson", "public_transport"),
                        ("car_zones.geojson", "driving")):
        p = ROOT / "data" / "out" / fname
        if not p.exists():
            continue
        gj = json.loads(p.read_text(encoding="utf-8"))
        for f in gj.get("features", []):
            pr = f.get("properties", {})
            key = (pr.get("school_id"), mode, pr.get("min"))
            if all(k is not None for k in key):
                zones[key] = shape(f["geometry"])
    return zones


def hhmm_from_minutes(minutes_after_midnight: int) -> str:
    return f"{minutes_after_midnight // 60:02d}:{minutes_after_midnight % 60:02d}"


def extract_pt(routes: list) -> dict:
    """Из ответа pt/2.0: первый маршрут → длительность, пересадки, коридоры."""
    if not isinstance(routes, list) or not routes:
        return {"status": "ERR", "note": "пустой ответ"}
    r = routes[0]
    corridors = set()
    for m in r.get("movements", []):
        for key in ("metro", "bus", "tram", "trolleybus", "suburban_train",
                    "mcd", "mcc", "shuttle_bus"):
            block = m.get(key)
            if isinstance(block, dict) and block.get("line_name"):
                corridors.add(block["line_name"])
            elif isinstance(block, dict) and (block.get("name") or block.get("number")):
                corridors.add(str(block.get("name") or block.get("number")))
    return {
        "duration_sec": r.get("total_duration"),
        "transfer_count": r.get("transfer_count"),
        "transports": ";".join(r.get("transport") or []),
        "corridors": ";".join(sorted(corridors)),
    }


def extract_driving(resp: dict) -> dict:
    """Из ответа routing/7.0.0 (output=summary): result[0].duration."""
    res = resp.get("result") if isinstance(resp, dict) else None
    if isinstance(res, list) and res:
        r0 = res[0]
        return {
            "duration_sec": r0.get("duration"),
            "transfer_count": "",
            "transports": "driving",
            "corridors": "",
        }
    return {"status": "ERR", "note": f"неожиданный формат: {str(resp)[:200]}"}


def load_done() -> dict:
    if not OUT_CSV.exists():
        return {}
    rows = list(csv.DictReader(OUT_CSV.read_text(encoding="utf-8-sig").splitlines()))
    return {r["lobe_id"]: r for r in rows}


def save_row(row: dict) -> None:
    exists = OUT_CSV.exists()
    with OUT_CSV.open("a", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLS)
        if not exists:
            w.writeheader()
        w.writerow(row)


def verdict_of(ratio: float, mode: str) -> str:
    if ratio <= 1.2:
        return "подтверждено"
    if ratio <= 1.5:
        return "частично"
    return "противоречит" if mode == "public_transport" else "противоречит (caveat авто)"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="максимум НОВЫХ запросов (0 = без лимита)")
    args = ap.parse_args()

    cfg = load_config()
    date = cfg["date"]
    schools = load_schools()
    lobes = load_lobes()
    meta = load_review_meta()
    done = load_done()
    zones = load_zones()

    # порядок: сначала ВСЕ public_transport (приоритет этапа цен), затем driving —
    # per-minute окно (~25/мин) у routing-семейства ОБЩЕЕ, а пейсинг клиента per-service;
    # чередование режимов давало комбинированную частоту >25/мин (429 04.11). Внутри
    # режима — порядок таблицы lobes_review.md (сначала «только у ОТ»).
    order_key = {}
    for lb in lobes:
        m = meta.get(lb["lobe_id"], {})
        order_key[lb["lobe_id"]] = (m.get("table_order", 10**9))
    lobes.sort(key=lambda lb: (
        0 if lb["mode_api"] == "public_transport" else 1,
        order_key[lb["lobe_id"]], lb["lobe_id"]))

    pt_start_unix = client.msk_to_unix(date, "08:30")  # = 05:30Z, семантика зон «от школы»
    new_requests = 0
    skipped = 0

    for lb in lobes:
        lobe_id = lb["lobe_id"]
        if lobe_id in done and done[lobe_id]["status"] != "ERR":
            skipped += 1
            continue
        m = meta.get(lobe_id, {})
        sch = schools.get(lb["school_id"])
        if not sch:
            print(f"[skip] нет школы {lb['school_id']} ({lobe_id})")
            continue
        lat, lon = float(sch["lat"]), float(sch["lon"])
        az = float(lb["azimuth"])
        r_km = float(lb["r_max_km"])
        min_min = int(lb["min"])
        mode = lb["mode_api"]
        elat, elon = lobe_tip(zones, lb["school_id"], mode, min_min, lat, lon, az, r_km)

        row = {
            "table_order": m.get("table_order", ""),
            "lobe_id": lobe_id,
            "school_id": lb["school_id"],
            "school_name": sch["name"],
            "mode": mode,
            "min": min_min,
            "azimuth_csv": az,
            "compass_az": m.get("compass_az", ""),
            "r_km": r_km,
            "endpoint_lat": f"{elat:.6f}",
            "endpoint_lon": f"{elon:.6f}",
            "status": "", "duration_sec": "", "ratio": "",
            "transfer_count": "", "transports": "", "corridors": "",
            "verdict": "", "note": "",
            "hypothesis": m.get("hypothesis", ""),
            "check_hint": m.get("check_hint", ""),
            "confidence": m.get("confidence", ""),
        }

        try:
            if mode == "public_transport":
                resp = client.public_transport_route(
                    f"{lon},{lat}", f"{elon},{elat}", pt_start_unix, enable_schedule=True,
                    transports=["metro", "bus", "trolleybus", "tram"])
            else:
                departure = hhmm_from_minutes(8 * 60 + 30 - min_min)
                utc_unix = client.msk_to_unix(date, departure)
                resp = client.directions_driving(f"{lon},{lat}", f"{elon},{elat}", utc_unix)
        except client.QuotaExhaustedError as e:
            print(f"[stop] лимит/429: {e}")
            break
        except Exception as e:  # сетевые сбои — сохраняем, ретрай в следующий запуск
            row["status"] = "ERR"
            row["note"] = f"{type(e).__name__}: {e}"[:200]
            save_row(row)
            print(f"[ERR] {lobe_id}: {row['note']}")
            continue

        row["status"] = str(resp["status"])
        if resp["status"] == 200:
            parsed = extract_pt(resp["data"]) if mode == "public_transport" else extract_driving(resp["data"])
            row.update({k: parsed.get(k, "") for k in
                        ("duration_sec", "transfer_count", "transports", "corridors")})
            if parsed.get("duration_sec"):
                ratio = parsed["duration_sec"] / (min_min * 60)
                row["ratio"] = f"{ratio:.2f}"
                row["verdict"] = verdict_of(ratio, mode)
            else:
                row["note"] = parsed.get("note", "")
                row["status"] = parsed.get("status", row["status"])
        elif resp["status"] == 400:
            row["note"] = "400: параметры не приняты"
        elif resp["status"] == 403:
            row["note"] = "403: ключ недействителен"
        else:
            row["note"] = f"HTTP {resp['status']}"
        save_row(row)
        new_requests += 1
        print(f"[ok] #{m.get('table_order','?')} {lobe_id} {mode} {min_min}мин "
              f"status={row['status']} dur={row['duration_sec']} ratio={row['ratio']} "
              f"verdict={row['verdict']}")

        # пауза 0.5с ПОВЕРХ per-service пейсинга клиента (4.5с) → ~5с/запрос ≈ 12/мин.
        # Так держимся ниже окна ~20/мин, сработавшего 05.11 на 3.0с+1.2с.
        import time as _t
        _t.sleep(0.5)

        if args.limit and new_requests >= args.limit:
            print(f"[stop] достигнут --limit {args.limit}")
            break

    done2 = load_done()
    print(f"\nИтог прогона: новых запросов {new_requests}, скипнуто {skipped}, "
          f"в CSV строк: {len(done2)}")
    report = client.budget_report()
    print("Бюджет:", json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
