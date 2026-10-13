"""Батчи для суб-агентов: 89 лепестков с ИСТИННЫМИ компасными бэрингами (90-az)
+ vision-landmark'и только для совпавших маркеров (Δ≤30°).
Выход: reports/plots/stage7/review_batches/batch_1..4.json
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
BDIR.mkdir(exist_ok=True)

schools = {}
with open(ROOT / "config" / "schools.csv", encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        if r["selected"] == "1":
            schools[r["entity_id"]] = {"name": r["name"], "address": r.get("address", ""),
                                       "lat": r["lat"], "lon": r["lon"]}

geo = json.loads((SDIR / "geometry_check.json").read_text(encoding="utf-8"))


def parse_vision(raw):
    import re
    s = raw.strip()
    s = re.sub(r"^```(?:json)?\s*", "", s)
    s = re.sub(r"\s*```$", "", s)
    i, j = s.find("{"), s.rfind("}")
    if i < 0 or j <= i:
        return {}
    try:
        return json.loads(s[i:j + 1])
    except json.JSONDecodeError:
        return {}


def circ_diff(a, b):
    d = abs(a - b) % 360.0
    return min(d, 360.0 - d)


def dir_ru(bearing):
    names = ["север", "северо-северо-восток", "северо-восток", "востоко-северо-восток",
             "восток", "востоко-юго-восток", "юго-восток", "юго-юго-восток",
             "юг", "юго-юго-запад", "юго-запад", "западо-юго-запад",
             "запад", "западо-северо-запад", "северо-запад", "северо-северо-запад"]
    return names[round((bearing % 360) / 22.5) % 16]


def load_reviews():
    rev = {}
    for f in sorted(SDIR.glob("reviews_[0-9].json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        for r in data.get("reviews", []):
            rev[r["lobe_id"]] = r
    return rev


def main():
    reviews = load_reviews()
    # vision landmarks per frame
    vis = {}
    for f in sorted((SDIR / "vision_raw").glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        if d.get("status") != "ok":
            continue
        vj = parse_vision(d.get("raw", ""))
        ms = []
        for m in vj.get("markers", []):
            if not isinstance(m, dict):
                continue
            try:
                deg = float(m.get("dir_deg", m.get("dir")))
            except (TypeError, ValueError):
                continue
            ms.append({"dir": deg, "landmark": m.get("landmark", ""),
                       "direction_ru": m.get("direction_ru", ""),
                       "r_km_est": m.get("r_km_est", "")})
        vis[f.stem] = {"markers": ms, "corridors": vj.get("corridors", []),
                       "anomalies": vj.get("anomalies", ""),
                       "zone_shape": vj.get("zone_shape", ""),
                       "school_area": vj.get("school_area", "")}

    items = []
    for key, g in sorted(geo.items()):
        mode, sid = key.split("__", 1)
        sch = schools[sid]
        lobes = g["lobes"]
        v = vis.get(key, {})
        ms = list(v.get("markers", []))
        used = set()
        for lb in lobes:
            brg = lb["bearing_compass"]
            best, best_d = None, 31.0
            for mi, m in enumerate(ms):
                if mi in used:
                    continue
                d = circ_diff(m["dir"], brg)
                if d < best_d:
                    best, best_d = mi, d
            lm = ""
            if best is not None:
                used.add(best)
                lm = ms[best].get("landmark", "")
            rv = reviews.get(lb["lobe_id"], {})
            items.append({
                "lobe_id": lb["lobe_id"],
                "number": lb["number"],
                "school_id": sid,
                "school": sch["name"],
                "school_latlon": f"{sch['lat']},{sch['lon']}",
                "address": sch["address"],
                "mode": mode,
                "min": rv.get("min", ""),
                "az_plane_csv": lb["az_csv"],
                "bearing_true": brg,
                "direction_ru": dir_ru(brg),
                "r_max_km": rv.get("r_max_km", ""),
                "old_hypothesis_ru": rv.get("hypothesis_ru", ""),
                "old_direction_ru": rv.get("direction_ru", ""),
                "old_confidence": rv.get("confidence", ""),
                "old_check_hint": rv.get("check_hint", ""),
                "vision_landmark": lm,
                "frame_anomalies": v.get("anomalies", ""),
                "frame_corridors": v.get("corridors", []),
                "marker_overlap_px": lb.get("nearest_marker_px"),
            })
    # 4 батча
    n = len(items)
    print(f"всего лепестков: {n}")
    per = (n + 3) // 4
    for i in range(4):
        chunk = items[i * per:(i + 1) * per]
        fn = BDIR / f"batch_{i + 1}.json"
        fn.write_text(json.dumps({"items": chunk}, ensure_ascii=False, indent=1),
                      encoding="utf-8")
        print(f"{fn.name}: {len(chunk)} лепестков")


if __name__ == "__main__":
    main()
