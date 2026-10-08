"""Стадия 1: config/schools.csv из канона school-portal (upstream-снапшот).

Школа = сущность kind blue/red с точкой entity=='school'. Для многофилиальных берётся главное
здание (первая school-точка). coord_quality: verified (не заглушка) | stub (kind_source 'portal 08.10').
Поле selected отмечает черновик 20 для Гейта 1 (Л2Ш + ЮЗАО/ЗАО).
"""
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UPSTREAM = next((ROOT / "data" / "upstream").glob("entities_*.json"))

data = json.loads(UPSTREAM.read_text(encoding="utf-8"))
entities = data["entities"]

# id черновика (ТЗ v2, Стадия 1): Л2Ш + ЮЗАО/ЗАО
SELECTED = {
    "лицей-вторая-школа-в-ф-овчинникова",  # Л2Ш — по запросу владельца
    # ЮЗАО
    "лицей-1533-лит", "школа-1514", "школа-192", "школа-1534-академическая-школа-1534",
    "школа-1158", "бауманская-инженерная-школа-1580", "школа-2007-фмш", "школа-1532",
    "школа-109", "московская-гимназия-на-юго-западе-1543-ю-в-завельского",
    # ЗАО
    "школа-1448-шуваловская-школа-1448", "университетская-гимназия-мгу", "школа-67",
    "образовательный-центр-протон", "ломоносовская-школа", "новая-школа",
    "школа-1329", "тор-it-school", "школа-на-проспекте-вернадского",
    # запасные (если владелец заменит кого-то): школа-1317, сунц-мгу, школа-1535 (ЦАО), школа-57 (ЦАО)
}

rows = []
for e in entities:
    if e.get("kind") not in ("blue", "red"):
        continue
    pts = [p for p in e.get("points", []) if p.get("entity") == "school"]
    if not pts:
        continue
    p = pts[0]
    ks = str(e.get("kind_source", ""))
    rows.append({
        "entity_id": e["id"],
        "point_id": p.get("id", ""),
        "name": p.get("name") or e.get("name", ""),
        "address": p.get("address", ""),
        "lat": p.get("lat"),
        "lon": p.get("lon"),
        "kind": e.get("kind"),
        "kind_source": ks[:80],
        "coord_quality": "stub" if ks.startswith("portal 08.10") else "verified",
        "selected": 1 if e["id"] in SELECTED else 0,
    })

missing = SELECTED - {r["entity_id"] for r in rows}
if missing:
    print("НЕ НАЙДЕНЫ в каноне:", missing, file=sys.stderr)
    sys.exit(1)

rows.sort(key=lambda r: (-r["selected"], r["lat"] or 0))
out = ROOT / "config" / "schools.csv"
with open(out, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)

sel = [r for r in rows if r["selected"]]
print(f"всего школ в CSV: {len(rows)} (blue/red school-сущностей канона)")
print(f"отобрано: {len(sel)} (verified {sum(1 for r in sel if r['coord_quality']=='verified')}, "
      f"stub {sum(1 for r in sel if r['coord_quality']=='stub')})")
print(f"blue {sum(1 for r in sel if r['kind']=='blue')}, red {sum(1 for r in sel if r['kind']=='red')}")
print("записан:", out)
