"""Оценка качества vision-ответов: совпадение dir_deg модели с истинными бэрингами
(компас = 90-az из geometry_check.json). Отчёт + per-frame verdict read_ok/partial/misread.
"""
import json
import sys
import io
import math
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
SDIR = ROOT / "reports" / "plots" / "stage7"


def circ_diff(a, b):
    d = abs(a - b) % 360.0
    return min(d, 360.0 - d)


def parse_vision_raw(raw):
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


def main():
    geo = json.loads((SDIR / "geometry_check.json").read_text(encoding="utf-8"))
    out = {}
    for f in sorted((SDIR / "vision_raw").glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        if d.get("status") != "ok" or not d.get("raw"):
            out[f.stem] = {"verdict": "err"}
            continue
        vj = parse_vision_raw(d["raw"])
        g = geo.get(f.stem, {})
        true_brgs = [lb["bearing_compass"] for lb in g.get("lobes", [])]
        ms = []
        for m in vj.get("markers", []):
            if not isinstance(m, dict):
                continue
            try:
                deg = float(m.get("dir_deg", m.get("dir")))
            except (TypeError, ValueError):
                continue
            dmin = min((circ_diff(deg, tb) for tb in true_brgs), default=180.0)
            ms.append({"dir": deg, "dmin": round(dmin, 1)})
        n = len(ms)
        matched = sum(1 for m in ms if m["dmin"] <= 30)
        if n == 0:
            verdict = "no_markers"
        elif matched == n:
            verdict = "read_ok"
        elif matched >= max(1, n - 1):
            verdict = "partial"
        else:
            verdict = "misread"
        out[f.stem] = {"verdict": verdict, "n_markers": n, "matched": matched,
                       "markers": ms, "corridors": vj.get("corridors", []),
                       "anomalies": vj.get("anomalies", ""),
                       "school_area": vj.get("school_area", ""),
                       "zone_shape": vj.get("zone_shape", "")}
        print(f"{f.stem:48s} {verdict:10s} matched={matched}/{n}")
    (SDIR / "vision_raw" / "_quality.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("написано: vision_raw/_quality.json")


if __name__ == "__main__":
    main()
