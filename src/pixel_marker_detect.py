"""Детерминированное пиксельное определение маркеров лепестков (PIL/numpy).

Вход: stage7_frames.csv + PNG. Выход: reports/plots/stage7/pixel_markers.json
{key: {school_marker: [x,y], markers: [{dir_deg, x, y, area, bbox_w, bbox_h}], n_lobes_manifest}}
Компасный азимут от зелёного маркера школы: 0=север, по часовой (север = вверх кадра).
"""
import csv
import json
import math
import sys
import io
from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
SDIR = ROOT / "reports" / "plots" / "stage7"
OUT = SDIR / "pixel_markers.json"


def clusters_from_mask(mask, min_area, max_area, max_wh_ratio=3.5):
    """Связные компоненты (8-соседство) с фильтром площади и формы."""
    h, w = mask.shape
    seen = np.zeros_like(mask, dtype=bool)
    out = []
    for y0 in range(h):
        for x0 in range(w):
            if not mask[y0, x0] or seen[y0, x0]:
                continue
            q = deque([(x0, y0)])
            seen[y0, x0] = True
            pts = []
            while q:
                x, y = q.popleft()
                pts.append((x, y))
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        nx, ny = x + dx, y + dy
                        if 0 <= nx < w and 0 <= ny < h and mask[ny, nx] and not seen[ny, nx]:
                            seen[ny, nx] = True
                            q.append((nx, ny))
            if len(pts) < min_area:
                continue
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            bw, bh = max(xs) - min(xs) + 1, max(ys) - min(ys) + 1
            area = len(pts)
            if area > max_area:
                continue
            if max(bw, bh) / max(min(bw, bh), 1) > max_wh_ratio:
                continue
            cx, cy = sum(xs) / area, sum(ys) / area
            out.append({"x": round(cx, 1), "y": round(cy, 1), "area": area,
                        "bbox_w": bw, "bbox_h": bh})
    return out


def analyze(path):
    img = np.array(Image.open(path).convert("RGB")).astype(int)
    r, g, b = img[:, :, 0], img[:, :, 1], img[:, :, 2]
    # зелёный маркер школы
    green = (g > 100) & (g > r + 30) & (g > b + 30)
    gc = clusters_from_mask(green, min_area=30, max_area=100000, max_wh_ratio=5)
    if not gc:
        return None, 0
    g0 = max(gc, key=lambda c: c["area"])
    # синие нумерованные маркеры
    blue = (b > 150) & (r < 100) & (g < 130) & (b > r + 80) & (b > g + 60)
    mc = clusters_from_mask(blue, min_area=5, max_area=600)
    marks = []
    for c in mc:
        dx, dy = c["x"] - g0["x"], c["y"] - g0["y"]
        bearing = math.degrees(math.atan2(dx, -dy)) % 360
        marks.append({**c, "dir_deg": round(bearing, 1)})
    marks.sort(key=lambda m: m["dir_deg"])
    return (g0, marks), int(green.sum())


def main():
    rows = []
    with open(SDIR / "stage7_frames.csv", newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if r["mode"] in ("car", "pt") and r["school_id"] != "OVERVIEW":
                rows.append(r)
    out = {}
    bad = []
    for r in rows:
        key = f"{r['mode']}__{r['school_id']}"
        path = SDIR / r["frame"]
        (g0, marks), green_px = analyze(path)
        n_lobes = r["lobes"].count('"lobe_id"')
        if g0 is None:
            bad.append((key, "нет зелёного маркера"))
            out[key] = {"school_marker": None, "markers": [], "n_lobes_manifest": n_lobes}
            continue
        out[key] = {"school_marker": [g0["x"], g0["y"], g0["area"]],
                    "markers": marks, "n_lobes_manifest": n_lobes}
        flag = "" if len(marks) == n_lobes else f"  <-- {len(marks)} vs {n_lobes}"
        print(f"{key:50s} lobes={n_lobes} markers={len(marks)}{flag}")
        for m in marks:
            print(f"    {m['dir_deg']:6.1f}°  ({m['x']},{m['y']}) area={m['area']}")
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nbad: {bad}")
    print(f"написано: {OUT}")


if __name__ == "__main__":
    main()
