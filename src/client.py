"""Клиент 2ГИС: кэш по хэшу запроса (без ключа), учёт бюджета по сервисам, стоп по резерву.

Правила (ТЗ v2, §ПРАВИЛА):
- ключ только из env '2GIS_API_KEY' или реестра User (никогда не пишем в файлы/логи);
- сырые ответы: data/raw/<service>/<sha1(запрос без ключа)>.json (бинарные — .bin + мета .json);
- повторный запрос с тем же хэшем идёт из кэша и бюджет не тратит;
- журнал: data/db/experiments.sqlite (таблица requests), версия методики v1;
- остаток < reserve по сервису → исключение BudgetReserveError.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
DB_PATH = ROOT / "data" / "db" / "experiments.sqlite"

SERVICES = ("geocoder", "routing", "public_transport", "distance_matrix", "isochrone", "static_maps")
BUDGET_LIMIT = 1000
RESERVE = 100
METHOD_VERSION = "v1"

# Эндпоинты подтверждены Context7 (/2gis/docs-mirror) 08.10; спорные — помечены, проверка экспериментом.
BASE_URLS = {
    "geocoder": "https://catalog.api.2gis.com/3.0/items/geocode",
    "routing": "https://routing.api.2gis.com/routing/7.0.0/global",          # POST
    "public_transport": "https://routing.api.2gis.com/public_transport/2.0",  # POST
    "distance_matrix": "https://routing.api.2gis.com/get_dist_matrix",        # POST ?version=2.0
    "isochrone": "https://routing.api.2gis.com/isochrone/2.0.0",              # POST
    "static_maps": "https://static.maps.2gis.com/2.0",                        # GET, PNG
}


class BudgetReserveError(RuntimeError):
    pass


def get_key() -> str:
    k = os.environ.get("2GIS_API_KEY")
    if k:
        return k
    if sys.platform == "win32":
        import winreg
        try:
            return winreg.QueryValueEx(
                winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment"), "2GIS_API_KEY"
            )[0]
        except OSError:
            pass
    raise RuntimeError("2GIS_API_KEY не найден ни в env, ни в реестре User")


def msk_to_utc(date_iso: str, hhmm_msk: str) -> str:
    """'2026-10-14', '08:30' -> '2026-10-14T05:30:00Z' (МСК = UTC+3)."""
    d = datetime.fromisoformat(f"{date_iso}T{hhmm_msk}:00")
    return (d - timedelta(hours=3)).isoformat() + "Z"


def msk_to_unix(date_iso: str, hhmm_msk: str) -> int:
    d = datetime.fromisoformat(f"{date_iso}T{hhmm_msk}:00")
    return int((d - timedelta(hours=3)).replace(tzinfo=timezone.utc).timestamp())


def _db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.execute(
        """CREATE TABLE IF NOT EXISTS requests(
             id INTEGER PRIMARY KEY, service TEXT, request_hash TEXT, url_no_key TEXT,
             status TEXT, utc_time TEXT, cached INTEGER, method_version TEXT)"""
    )
    con.execute("CREATE TABLE IF NOT EXISTS isochrones(id INTEGER PRIMARY KEY, school_id TEXT, min INTEGER, mode TEXT, request_hash TEXT, method_version TEXT)")
    con.execute("CREATE TABLE IF NOT EXISTS probes(id INTEGER PRIMARY KEY, school_id TEXT, mode TEXT, hypothesis TEXT, t_sec REAL, method_version TEXT)")
    con.execute("CREATE TABLE IF NOT EXISTS verdicts(id INTEGER PRIMARY KEY, gate TEXT, result TEXT, note TEXT, utc_time TEXT)")
    con.commit()
    return con


def _canonical(service: str, url_no_key: str, body_no_key: str = "") -> str:
    """Каноническая строка для хэша: всё без ключа."""
    return f"{service}|{url_no_key}|{body_no_key}"


def _cache_path(service: str, h: str, binary: bool) -> Path:
    return RAW / service / (f"{h}.bin" if binary else f"{h}.json")


def _log_request(service: str, h: str, url_no_key: str, status: str, cached: bool):
    con = _db()
    con.execute(
        "INSERT INTO requests(service, request_hash, url_no_key, status, utc_time, cached, method_version) VALUES(?,?,?,?,?,?,?)",
        (service, h, url_no_key[:500], str(status), datetime.now(timezone.utc).isoformat(), int(cached), METHOD_VERSION),
    )
    con.commit()
    con.close()


def _spent(service: str) -> int:
    con = _db()
    n = con.execute("SELECT COUNT(*) FROM requests WHERE service=? AND cached=0", (service,)).fetchone()[0]
    con.close()
    return n


def _check_budget(service: str) -> int:
    remaining = BUDGET_LIMIT - _spent(service)
    if remaining - 1 < RESERVE:
        raise BudgetReserveError(
            f"Стоп: остаток {remaining} по сервису {service} меньше резерва {RESERVE} — сообщи владельцу"
        )
    return remaining


_last_call: dict[str, float] = {}
_PACING = {"routing": 1.5, "public_transport": 1.5, "distance_matrix": 1.5,
           "isochrone": 0.3, "geocoder": 0.15, "static_maps": 0.3}
# Лимит демо-ключа: ~50 запросов/мин на routing-семейство (поймано 429 после 50, 08.10) — пейсинг обязателен.


def _request(service: str, url_no_key: str, body_no_key: str = "", binary: bool = False, timeout: int = 60):
    """GET (body пуст) или POST (body задан) с кэшем, учётом бюджета, пейсингом и ретраем 429."""
    if service not in SERVICES:
        raise ValueError(f"Неизвестный сервис {service}")
    h = hashlib.sha1(_canonical(service, url_no_key, body_no_key).encode("utf-8")).hexdigest()
    cp = _cache_path(service, h, binary)
    if cp.exists():
        meta = json.loads(cp.with_suffix(".json").read_text(encoding="utf-8")) if binary else json.loads(cp.read_text(encoding="utf-8"))
        # кэш переиспользуем ТОЛЬКО для успешных ответов: ошибки (429/400/ERR) ретраятся вживую
        if meta.get("status") == 200:
            _log_request(service, h, url_no_key, "cache", cached=True)
            if binary:
                return {"cached": True, "status": meta["status"], "data": cp.read_bytes(), "meta": meta}
            return {"cached": True, "status": meta["status"], "data": meta["response"], "meta": meta}

    remaining = _check_budget(service)
    key = get_key()
    sep = "&" if "?" in url_no_key else "?"
    url = f"{url_no_key}{sep}key={urllib.parse.quote(key)}"

    # пейсинг (лимит ~50/мин)
    import time as _time
    wait = _PACING.get(service, 0.2) - (_time.time() - _last_call.get(service, 0))
    if wait > 0:
        _time.sleep(wait)
    _last_call[service] = _time.time()

    headers = {"User-Agent": "school-transport/0.1"}
    if body_no_key:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body_no_key.encode("utf-8") if body_no_key else None, headers=headers)

    attempt, status, payload = 0, None, b""
    while attempt < 4:
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                status, payload = r.status, r.read()
            break
        except urllib.error.HTTPError as e:
            status, payload = e.code, e.read()
            if e.code == 429 and attempt < 3:
                attempt += 1
                _time.sleep(3 * attempt)
                continue
            break
        except Exception as e:  # сетевые сбои — тоже сохраняем
            status, payload = "ERR", f"{type(e).__name__}: {e}".encode("utf-8")
            break

    RAW.joinpath(service).mkdir(parents=True, exist_ok=True)
    meta = {"service": service, "request_no_key": url_no_key, "body_no_key": body_no_key,
            "request_hash": h, "status": status,
            "utc_time": datetime.now(timezone.utc).isoformat(), "method_version": METHOD_VERSION,
            "remaining_before": remaining}
    if binary:
        cp.write_bytes(payload)
        cp.with_suffix(".json").write_text(json.dumps({**meta, "size": len(payload)}, ensure_ascii=False, indent=2), encoding="utf-8")
        parsed = None
    else:
        try:
            parsed = json.loads(payload.decode("utf-8"))
        except Exception:
            parsed = payload.decode("utf-8", errors="replace")[:2000]
        cp.write_text(json.dumps({**meta, "response": parsed}, ensure_ascii=False, indent=2), encoding="utf-8")

    _log_request(service, h, url_no_key, status, cached=False)
    return {"cached": False, "status": status, "data": payload if binary else parsed, "meta": meta,
            "request_hash": h, "remaining_before": remaining}


# ---- тонкие обёртки (сигнатуры — по докам Context7 08.10; неподтверждённое помечено) ----

def geocode(q: str, fields: str = "items.point,items.name"):
    params = urllib.parse.urlencode({"q": q, "fields": fields, "locale": "ru_RU"})
    return _request("geocoder", f"{BASE_URLS['geocoder']}?{params}")


def isochrone(*, lat, lon, durations, transport="driving", reverse=False, start_time=None,
              public_transport_types=None, output_format="wkt"):
    """POST /isochrone/2.0.0. reverse — только driving (в UI доков отключается для ОТ — проверить Стадией 3)."""
    body = {"start": {"lat": lat, "lon": lon}, "durations": durations, "transport": transport}
    if transport == "driving":
        body["reverse"] = bool(reverse)
    if start_time:
        body["start_time"] = start_time
    if public_transport_types:
        body["public_transport_types"] = public_transport_types
    body["format"] = output_format
    return _request("isochrone", BASE_URLS["isochrone"], json.dumps(body, sort_keys=True))


def directions_driving(start_lonlat: str, finish_lonlat: str, utc_unix: int | None = None,
                       traffic_mode: str = "statistics", output: str = "summary"):
    """POST /routing/7.0.0/global. utc — Unix отправления (проверить, что именно отправления)."""
    pts = [{"type": "stop", "lon": float(p.split(",")[0]), "lat": float(p.split(",")[1])}
           for p in (start_lonlat, finish_lonlat)]
    body = {"points": pts, "transport": "driving", "output": output, "traffic_mode": traffic_mode, "locale": "ru"}
    if utc_unix:
        body["utc"] = utc_unix
    return _request("routing", BASE_URLS["routing"], json.dumps(body, sort_keys=True))


def public_transport_route(start_lonlat: str, finish_lonlat: str, start_time_unix: int,
                           enable_schedule: bool = True, transports: list[str] | None = None):
    """POST /public_transport/2.0. start_time — Unix отправления."""
    body = {
        "source": {"point": {"lat": float(start_lonlat.split(",")[1]), "lon": float(start_lonlat.split(",")[0])}},
        "target": {"point": {"lat": float(finish_lonlat.split(",")[1]), "lon": float(finish_lonlat.split(",")[0])}},
        "start_time": start_time_unix,
        "enable_schedule": enable_schedule,
        "locale": "ru",
    }
    if transports:
        body["transport"] = transports
    return _request("public_transport", BASE_URLS["public_transport"], json.dumps(body, sort_keys=True))


def distance_matrix(points: list[dict], sources: list[int], targets: list[int],
                    traffic_mode: str | None = None, utc_unix: int | None = None):
    """POST /get_dist_matrix?version=2.0. points: [{lat,lon}]. Лимит: ≤25 в sources/targets, ≤2000 км.
    Параметры пробок/времени НЕ подтверждены доками — проверить экспериментом."""
    body: dict = {"points": points, "sources": sources, "targets": targets}
    if traffic_mode:
        body["traffic_mode"] = traffic_mode
    if utc_unix:
        body["utc"] = utc_unix
    return _request("distance_matrix", f"{BASE_URLS['distance_matrix']}?version=2.0", json.dumps(body, sort_keys=True))


def static_map(center_latlon: str, zoom: int, size: str = "800x600", markers: str | None = None,
               polylines: str | None = None, polygons: str | None = None):
    """GET /2.0. Параметры: s, c (lat,lon), z, pt (маркеры), ls (линии), pn (ПОЛИГОНЫ), key.
    Полигоны ПОДДЕРЖИВАЮТСЯ (pn) — Стадия 7 может рисовать зоны нативно."""
    params = {"s": size, "c": center_latlon, "z": zoom, "locale": "ru_RU"}
    if markers:
        params["pt"] = markers
    if polylines:
        params["ls"] = polylines
    if polygons:
        params["pn"] = polygons
    return _request("static_maps", f"{BASE_URLS['static_maps']}?{urllib.parse.urlencode(params)}", binary=True)


def budget_report() -> dict:
    return {s: {"spent": _spent(s), "remaining": BUDGET_LIMIT - _spent(s)} for s in SERVICES}
