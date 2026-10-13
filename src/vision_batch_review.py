"""Пиксельный (vision) обзор 38 кадров stage7 через bothub deepseek-v4-flash-vision-exp.

Возобновляемый: результат каждого кадра пишется в reports/plots/stage7/vision_raw/<key>.json
сразу после вызова; существующие (status=ok) пропускаются. Ретраи 3× на не-200.
Без API 2ГИС — только bothub (ключ из C:/Users/volga/.hermes/.env).
"""
import base64
import csv
import json
import re
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
FRAMES = ROOT / "reports" / "plots" / "stage7" / "stage7_frames.csv"
OUT_DIR = ROOT / "reports" / "plots" / "stage7" / "vision_raw"
OUT_DIR.mkdir(exist_ok=True)

ENV = (Path.home() / ".hermes" / ".env").read_text(encoding="utf-8")
M = re.search(r"BOTHUB_API_KEY\s*=\s*(\S+)", ENV)
KEY = M.group(1).strip().strip('"').strip("'")
URL = "https://openai.bothub.ru/v1/chat/completions"
MODEL = "deepseek-v4-flash-vision-exp"

PROMPT = (
    "Ты анализируешь кадр статической карты 2ГИС (Москва и область) с зонами транспортной "
    "доступности школы. На карте: крупный ЗЕЛЁНЫЙ маркер школы (обычно в центре кадра), "
    "полупрозрачные цветные полигоны-зоны доступности (вложенные по времени: 20/25/30/35/40 мин), "
    "и круглые маркеры с БЕЛЫМИ ЦИФРАМИ на дальних концах вытянутых лепестков зоны. "
    "Задача — привязать лепестки к реальной географии. "
    "Ответь СТРОГО одним JSON-объектом (без markdown, без пояснений вне JSON) с полями:\n"
    '{"markers":[{"num":1,"dir_deg":172,"direction_ru":"юг","r_km_est":35,"landmark":"Подольск/Щербинка (если видно на краю)"}],'
    '"zone_shape":"округлая, вытянута с юга на север",'
    '"corridors":[{"kind":"автомагистраль|линия метро|ж.д.|шоссе|МЦД","name_or_hint":"название, если подписано, иначе пусто","direction_ru":"юг"}],'
    '"anomalies":"далёкие лепестки, асимметрия, зоны за МКАД и т.п.",'
    '"school_area":"район/станция метро рядом с зелёным маркером"}\n'
    "Правила: dir_deg — компасный азимут от школы (0=север, по часовой, целое число); "
    "markers перечисли ВСЕ, которые видишь, с цифрой, если она читается; "
    "не выдумывай подписи, которых не видишь — лучше landmark по районам/населённым пунктам; "
    "отвечай по-русски."
)


def frame_key(mode, school_id, frame):
    return f"{mode}__{school_id}"


def call_vision(img_b64):
    for attempt in range(3):
        try:
            r = requests.post(
                URL,
                headers={"Authorization": f"Bearer {KEY}"},
                timeout=180,
                json={
                    "model": MODEL,
                    "max_tokens": 1800,
                    "temperature": 0.2,
                    "messages": [{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": PROMPT},
                            {"type": "image_url",
                             "image_url": {"url": f"data:image/png;base64,{img_b64}"}},
                        ],
                    }],
                },
            )
            if r.status_code == 200:
                j = r.json()
                content = (j.get("choices") or [{}])[0].get("message", {}).get("content") or ""
                return {"status": "ok", "raw": content}
            err = f"HTTP {r.status_code}: {r.text[:200]}"
        except requests.RequestException as e:
            err = f"exc: {e}"
        print(f"  retry {attempt+1}: {err}", flush=True)
        time.sleep(10 * (attempt + 1))
    return {"status": "error", "raw": err}


def main():
    rows = []
    with open(FRAMES, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if r["mode"] in ("car", "pt") and r["school_id"] != "OVERVIEW":
                rows.append(r)
    print(f"кадров: {len(rows)}", flush=True)
    n_ok = n_err = n_skip = 0
    for r in rows:
        key = frame_key(r["mode"], r["school_id"], r["frame"])
        out = OUT_DIR / f"{key}.json"
        if out.exists():
            try:
                prev = json.loads(out.read_text(encoding="utf-8"))
                if prev.get("status") == "ok":
                    n_skip += 1
                    print(f"skip {key}", flush=True)
                    continue
            except Exception:
                pass
        img_path = ROOT / "reports" / "plots" / "stage7" / r["frame"]
        img_b64 = base64.b64encode(img_path.read_bytes()).decode()
        res = call_vision(img_b64)
        res.update({
            "key": key, "frame": r["frame"], "school_id": r["school_id"],
            "mode": r["mode"], "lobes_manifest": r["lobes"],
            "utc": time.strftime("%Y-%m-%d %H:%M:%S"),
        })
        out.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
        if res["status"] == "ok":
            n_ok += 1
            print(f"ok {key} ({len(res['raw'])} chars)", flush=True)
        else:
            n_err += 1
            print(f"ERR {key}", flush=True)
        time.sleep(3)
    print(f"DONE ok={n_ok} err={n_err} skip={n_skip}", flush=True)


if __name__ == "__main__":
    main()
