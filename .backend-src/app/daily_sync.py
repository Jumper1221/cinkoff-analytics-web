"""Ежедневный синк v2: инкремент по /go/api/public/orders/active/?startDate&endDate.

Правило (решение Михаила): СНАЧАЛА сырьё на диск, ПОТОМ БД. Ключ = расходник.

Порядок прогона (флаги-аргументы: orders|remnants|prices|dicts|all; по умолчанию all):
  1. orders    — шапки за окно (по умолчанию 3 дня) → snapshots/<stamp>/orders_delta.json.gz
                 + детали изменённых/новых → details_delta_*.json.gz (3 воркера, 0.05с)
                 → заливка в БД (upsert; услуги теперь с полями Serv)
  2. remnants  — срез остатков (всегда; 1 запрос) → remnants/<stamp>.json.gz → remnants_snapshots
  3. prices    — только по воскресеньям (или --prices): 66 пар → prices/<stamp>/... → prices_history
  4. dicts     — только по воскресеньям: branches/agreements/brands/groups → справочники

Идемпотентно: можно гнать повторно, дублей не будет (ON CONFLICT / upsert / DO NOTHING).
Запуск:  python -u daily_sync.py                  # всё, по расписанию-логике
         python -u daily_sync.py orders           # только заказы+детали
         python -u daily_sync.py remnants         # только остатки
         python -u daily_sync.py orders --days=7  # широкое окно (напр. после простоя)
         python -u daily_sync.py prices --force   # цены вне-воскресенья
"""
from __future__ import annotations

import concurrent.futures as cf
import gzip
import io
import json
import logging
import os
import sqlite3  # noqa:+F401 (не используется, но импорт-дешевле-удалить-потом)
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import requests

import db
import normalize as nz
import store

log = logging.getLogger("daily")

# ── Конфиг ───────────────────────────────────────────────────────────────────
API = "https://client.grandline.ru/api/public"
GAPI = "https://client.grandline.ru/go/api/public"
SNAP_ROOT = Path(__file__).resolve().parent.parent / "data" / "snapshots"
INCREMENT_DAYS = 3          # окно-инкремента-заказов (плюс-страховка)
DETAIL_WORKERS = 3          # как-в-stage0: 5.4-заказов/с
DETAIL_PAUSE = 0.05
RETRIES = 6

MSK = timezone(timedelta(hours=3))  # API-живёт-по-МСК


def _api_key() -> str:
    env = Path(__file__).resolve().parent.parent / ".env"
    for line in env.read_text(encoding="utf-8").splitlines():
        if line.startswith("API_KEY"):
            return line.split("=", 1)[1].strip()
    raise RuntimeError("API_KEY-не-найден-в-.Env")


KEY = _api_key()
S = requests.Session()
S.headers["User-Agent"] = "cinkoff-daily/1.0"


def fetch(url: str, **params):
    """GET-с-ретраями (сеть/429/5xx/обрыв-JSON); None-после-6-попыток."""
    params["api_key"] = KEY
    for att in range(RETRIES):
        try:
            r = S.get(url, params=params, timeout=(15, 120))
        except (requests.ConnectTimeout, requests.ReadTimeout, requests.ConnectionError):
            time.sleep(2 + 2 * att)
            continue
        if r.status_code == 429:
            time.sleep(2.5)
            continue
        if r.status_code == 200:
            try:
                return r.json()
            except Exception:
                time.sleep(2)
                continue
        if r.status_code in (500, 502, 503, 504):
            time.sleep(2 + 2 * att)
            continue
        log.warning("HTTP %s для %s: %s", r.status_code, url, r.text[:120])
        time.sleep(2)
    log.error("fetch-сдался: %s", url)
    return None


def today_msk() -> date:
    return datetime.now(MSK).date()


def stamp_dir(d: date | None = None) -> Path:
    d = d or today_msk()
    p = SNAP_ROOT / f"daily-{d.isoformat()}"
    (p / "details").mkdir(parents=True, exist_ok=True)
    (p / "remnants").mkdir(exist_ok=True)
    (p / "prices").mkdir(exist_ok=True)
    return p


def save_gz(path: Path, data) -> float:
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode()
    tmp = path.with_suffix(path.suffix + ".tmp")
    with gzip.open(tmp, "wb") as f:
        f.write(blob)
    tmp.rename(path)
    return len(blob) / 1e6


# ── 1. Заказы-инкремент ──────────────────────────────────────────────────────

def _last_sync_success(conn) -> "date | None":
    """Дата последнего успешного/частичного сина (по-снапшотам-статусов)."""
    with conn.cursor() as cur:
        cur.execute("SELECT MAX(snapshot_date)::date FROM order_status_history")
        row = cur.fetchone()
    return row[0] if row and row[0] else None


def sync_orders(conn, days: int = INCREMENT_DAYS, stamp: Path | None = None) -> dict:
    # авторасширение-окна: если-послед-срез-старше-окна-—-расширяем-до-него (+1-запас)
    try:
        last = _last_sync_success(conn)
        if last:
            gap = (today_msk() - last).days + 1
            if gap > days:
                log.info("послед-срез-был %s (%d дн назад) — расширяю-окно %d→%d",
                         last, gap, days, gap)
                days = gap
    except Exception:
        log.warning("не-смог-проверить-свежесть-среза — окно-осталось %d", days)
    stamp = stamp or stamp_dir()
    d1 = (today_msk() - timedelta(days=days)).isoformat()
    d2 = today_msk().isoformat()
    t0 = time.time()

    # 1.1 сырьё: шапки-инкремента
    rows = fetch(f"{GAPI}/orders/active/", startDate=d1, endDate=d2)
    if not isinstance(rows, list):
        log.error("orders/active-не-список: %s", str(rows)[:120])
        rows = []
    mb = save_gz(stamp / "orders_delta.json.gz", rows)
    log.info("orders[%s..%s]: %d шапок (%.2f MB) — сырьё-сохранено", d1, d2, len(rows), mb)

    # 1.2 какие-уже-есть-в-БД-и-с-какой-сигнатурой (детали-нужны-только-новым/изменённым)
    need_detail: list[int] = []
    known: dict[int, str] = {}
    if rows:
        with conn.cursor() as cur:
            ids = [int(r["order_id"]) for r in rows if r.get("order_id")]
            cur.execute("SELECT order_id, list_sig FROM orders WHERE order_id = ANY(%s)", (ids,))
            known = {int(a): (b or "") for a, b in cur.fetchall()}
        for r in rows:
            oid = int(r.get("order_id") or 0)
            if not oid:
                continue
            if known.get(oid, "") != nz.list_sig(r) or oid not in known:
                need_detail.append(oid)

    # 1.3 детали: сырьё-пачками-по-500 (3-воркера)
    detail_counts = {"fetched": 0, "skipped": 0, "errors": 0}
    details_by_oid: dict[int, dict] = {}
    if need_detail:
        def grab(oid: int):
            d = fetch(f"{API}/orders/{oid}/")
            if isinstance(d, dict):
                d["_order_id"] = oid
            return oid, d
        part = 500
        for pi in range(0, len(need_detail), part):
            chunk_ids = need_detail[pi:pi + part]
            t1 = time.time()
            with cf.ThreadPoolExecutor(max_workers=DETAIL_WORKERS) as ex:
                for oid, d in ex.map(grab, chunk_ids):
                    if isinstance(d, dict):
                        details_by_oid[oid] = d
                        detail_counts["fetched"] += 1
                    else:
                        detail_counts["errors"] += 1
            fn = stamp / "details" / f"details_delta_{pi // part:03d}.json.gz"
            good = {str(k): v for k, v in details_by_oid.items()
                    if k in set(chunk_ids)}
            # пишем-ТОЛЬКО-эту-пачку (details_by_oid-накопительный; отфильтруем-по-ids-пачки)
            part_rows = {}
            for oid in chunk_ids:
                if oid in details_by_oid:
                    part_rows[str(oid)] = details_by_oid[oid]
            mb2 = save_gz(fn, part_rows)
            rate = len(part_rows) / max(0.1, time.time() - t1)
            log.info("детали-пачка %d: %d шт (%.1f/с, %.2f MB) → %s",
                     pi // part + 1, len(part_rows), rate, mb2, fn.name)
            time.sleep(DETAIL_PAUSE)
    detail_counts["skipped"] = max(0, len(rows) - len(need_detail))
    log.info("детали: нужны %d, взято %d, пропущено %d, ошибок %d",
             len(need_detail), detail_counts["fetched"], detail_counts["skipped"], detail_counts["errors"])

    # 1.4 ЗАЛИВКА-В-БД (после-того-как-сырьё-на-диске!)
    stats = {"upserted": 0, "details": 0, "items": 0, "errors": 0}
    for r in rows:
        if not isinstance(r, dict) or not r.get("order_id"):
            continue
        try:
            oid = store.upsert_order(conn, store.build_order_payload(r, source="daily-list"))
            if r.get("shipment_info"):
                store.upsert_shipments(conn, oid, r["shipment_info"], source="list")
            store.snapshot_order(conn, oid)
            stats["upserted"] += 1
        except Exception as exc:
            conn.rollback()
            stats["errors"] += 1
            log.warning("заказ %s: %s", r.get("order_id"), str(exc)[:120])
    conn.commit()

    for oid, ddetail in details_by_oid.items():
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM orders WHERE order_id = %s", (oid,))
                row = cur.fetchone()
            if row:
                orders_id = row[0]
            else:
                orders_id = store.upsert_order(conn, store.build_order_payload(
                    {"order_id": oid}, detail=ddetail, source="daily-detail"))
            res = store.apply_detail(conn, orders_id, ddetail, source="daily")
            stats["items"] += res.get("items", 0) + res.get("demand_items", 0)
            # sales + shipment_processes (как-в-stage1_load.load_details)
            cur2 = conn.cursor()
            for kind, key2 in (("sale", "sales"), ("correction", "sales_correct")):
                for sl in (ddetail.get(key2) or []):
                    if not isinstance(sl, dict):
                        continue
                    cur2.execute("""INSERT INTO sales (orders_id, id_1c, number, sales_date, ware_sum,
                                        service_sum, total_sum, posted, deletion_mark, subcontractor, kind, raw)
                                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                                    ON CONFLICT (orders_id, id_1c, kind) DO UPDATE SET
                                      number=EXCLUDED.number, sales_date=EXCLUDED.sales_date,
                                      ware_sum=EXCLUDED.ware_sum, service_sum=EXCLUDED.service_sum,
                                      total_sum=EXCLUDED.total_sum, posted=EXCLUDED.posted,
                                      deletion_mark=EXCLUDED.deletion_mark, subcontractor=EXCLUDED.subcontractor,
                                      raw=EXCLUDED.raw, fetched_at=now()""",
                                 (orders_id, nz.text(sl.get("id_1c")), nz.text(sl.get("number")),
                                  nz.dt(sl.get("date")), nz.num(sl.get("wareSum")),
                                  nz.num(sl.get("serviceSum")), nz.num(sl.get("totalSum")),
                                  nz.bool01(sl.get("posted")), nz.bool01(sl.get("deletion_mark")),
                                  nz.text(sl.get("subContractor")), kind, nz.jdump(sl)))
            cur2.close()
            if ddetail.get("shipment_processes"):
                store.upsert_shipments(conn, orders_id, [
                    {"shipmentNumber": sp.get("registerNumber"),
                     "shipmentState": sp.get("vehicleState"),
                     "driverName": sp.get("driver"),
                     "driverPhones": sp.get("driverTelephones")}
                    for sp in ddetail["shipment_processes"] if isinstance(sp, dict)
                ], source="detail")
            with conn.cursor() as cur3:
                cur3.execute("UPDATE orders SET detail_hash=%s, detail_fetched_at=now() WHERE id=%s",
                             (nz.detail_fingerprint(ddetail), orders_id))
            stats["details"] += 1
        except Exception as exc:
            conn.rollback()
            stats["errors"] += 1
            log.warning("деталь %s: %s", oid, str(exc)[:120])
    conn.commit()
    # 1.5 срез-статусов ВСЕХ открытых заказов БД (не-только-инкрементного-окна!):
    # старение-зависших должно считаться по полным-дневным-срезам (2293-открытых-нуждаются-в-срезе-ежедневно)
    n_snap = 0
    import config as _cfg
    with conn.cursor() as cur:
        placeholders = ", ".join(["%s"] * len(_cfg.SNAPSHOT_EXCLUDE_STATUSES))
        cur.execute(f"""SELECT id, order_status FROM orders
                        WHERE order_status IS NOT NULL
                          AND order_status NOT IN ({placeholders})
                        ORDER BY id""", tuple(_cfg.SNAPSHOT_EXCLUDE_STATUSES))
        open_ids = [r[0] for r in cur.fetchall()]
    for oid2 in open_ids:
        if store.snapshot_order(conn, oid2):
            n_snap += 1
    conn.commit()
    log.info("срез-статусов: %d/%d открытых-заказов-посещены", n_snap, len(open_ids))
    stats["snapshots"] = n_snap

    stats["seconds"] = round(time.time() - t0, 1)
    log.info("ORDERS-ЗАЛИВКА: %s", stats)
    return stats


# ── 2. Остатки-срез (каждый-прогон) ─────────────────────────────────────────

def sync_remnants(conn, stamp: Path | None = None) -> int:
    import psycopg2.extras
    stamp = stamp or stamp_dir()
    t0 = time.time()
    rows = fetch(f"{API}/remnants/", offset=0)
    all_rows: list = []
    while isinstance(rows, list) and rows:
        all_rows.extend(rows)
        if len(rows) < 20000:
            break
        nxt = fetch(f"{API}/remnants/", offset=len(all_rows))
        if not isinstance(nxt, list) or not nxt:
            break
        rows = nxt
        time.sleep(0.4)
    if not all_rows:
        log.warning("remnants-пусто — пропускаю (БД-не-трогаю)")
        return 0
    mb = save_gz(stamp / "remnants" / f"remnants_{today_msk().isoformat()}.json.gz", all_rows)
    log.info("remnants-сырьё: %d записей (%.2f MB)", len(all_rows), mb)

    today = today_msk()
    batch = []
    for it in all_rows:
        if not isinstance(it, dict) or not it.get("nomenclature_id"):
            continue
        nid = it["nomenclature_id"]
        for kind, key in (("metall", "remnants_metall"), ("goods", "remnants_goods")):
            for storage_id, qty in (it.get(key) or {}).items():
                try:
                    q = int(qty or 0)
                except Exception:
                    q = 0
                batch.append((nid, storage_id, kind, q, None, today))
        for storage_id, dstr in (it.get("delivery_time") or {}).items():
            ddate = dstr[:10] if isinstance(dstr, str) and len(dstr) >= 10 else None
            batch.append((nid, storage_id, "delivery", 0, ddate, today))

    with conn.cursor() as cur:
        psycopg2.extras.execute_values(cur, """
            INSERT INTO remnants_snapshots (nomenclature_id, storage_id, kind, qty, delivery_date, snapshot_date)
            VALUES %s
            ON CONFLICT (nomenclature_id, storage_id, kind, snapshot_date) DO NOTHING""",
            batch, page_size=1000)
    conn.commit()
    log.info("REMNANTS: +%d строк (snapshot %s) за %.1fs", len(batch), today, time.time() - t0)
    return len(batch)


# ── 3. Цены (вс-00:00-МСК или --force) ──────────────────────────────────────

def sync_prices(conn, stamp: Path | None = None) -> int:
    import psycopg2.extras
    stamp = stamp or stamp_dir()
    t0 = time.time()
    branches = fetch(f"{API}/branches/") or []
    agreements = fetch(f"{API}/agreements/") or []
    if not isinstance(branches, list) or not isinstance(agreements, list):
        log.error("справочники-не-списки — цены-пропускаю")
        return 0

    def b2n(b): return (b.get("name") or b["id_1c"][:8]).replace("/", "-").replace(" ", "_")
    def a2n(a): return (a.get("name") or a["id_1c"][:8]).split(";")[0].strip().replace(" ", "_")

    total = 0
    for b in branches:
        for a in agreements:
            # пробник-валидности-пары (limit=1)
            probe = fetch(f"{API}/prices/", branch_id_1c=b["id_1c"], agreement_id_1c=a["id_1c"], offset=0)
            if not isinstance(probe, list) or not probe:
                continue
            dirname = f"prices__{b2n(b)[:40]}__{a2n(a)[:40]}"
            pdir = stamp / "prices" / dirname
            pdir.mkdir(parents=True, exist_ok=True)
            offset, pi, cnt = 0, 0, 0
            while True:
                d = fetch(f"{API}/prices/", branch_id_1c=b["id_1c"], agreement_id_1c=a["id_1c"], offset=offset)
                if not isinstance(d, list) or not d:
                    break
                save_gz(pdir / f"prices_{pi:03d}.json.gz", d)
                # сразу-в-БД (сырьё-уже-на-диске)
                batch = [(it.get("nomenclature_id"), b["id_1c"], a["id_1c"],
                          nz.num(it.get("price")), nz.num(it.get("discount")),
                          nz.num(it.get("discountPrice")), nz.dt(it.get("version_date")))
                         for it in d if isinstance(it, dict) and it.get("nomenclature_id")]
                if batch:
                    with conn.cursor() as cur:
                        psycopg2.extras.execute_values(cur, """
                            INSERT INTO prices_history (nomenclature_id, branch_id_1c, agreement_id_1c,
                                                        price, discount_pct, discount_price, version_date)
                            VALUES %s
                            ON CONFLICT (nomenclature_id, branch_id_1c, agreement_id_1c, price, discount_pct, discount_price)
                            DO UPDATE SET last_seen=CURRENT_DATE, version_date=EXCLUDED.version_date""",
                            batch, page_size=1000)
                    conn.commit()
                cnt += len(batch)
                total += len(batch)
                offset += 20000
                pi += 1
                if len(d) < 20000:
                    break
                time.sleep(0.6)
            log.info("  цены %s: %d строк", dirname[7:45], cnt)
    log.info("PRICES: +%d строк за %.0fs", total, time.time() - t0)
    return total


# ── 4. Справочники (вс) ─────────────────────────────────────────────────────

def sync_dicts(conn, stamp: Path | None = None) -> bool:
    stamp = stamp or stamp_dir()
    ok = True
    for name, path in (("branches", f"{API}/branches/"), ("agreements", f"{API}/agreements/"),
                       ("nomenclature_groups", f"{API}/nomenclature_groups/")):
        d = fetch(path)
        if not isinstance(d, list):
            ok = False
            continue
        with open(stamp / f"{name}.json", "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)
        log.info("%s: %d (сырьё-сохранено)", name, len(d))
    d = fetch(f"{GAPI}/vehicle-brands/")
    if isinstance(d, list):
        with open(stamp / "vehicle_brands.json", "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)

    # справочники-в-БД (branches/agreements/brands/groups)
    with conn.cursor() as cur:
        p = stamp / "branches.json"
        if p.exists():
            for b in json.loads(p.read_text(encoding="utf-8")):
                if not isinstance(b, dict) or not b.get("id_1c"):
                    continue
                cur.execute("""INSERT INTO branches (id_1c, code_1c, name, address, latitude, longitude, description)
                               VALUES (%s,%s,%s,%s,%s,%s,%s)
                               ON CONFLICT (id_1c) DO UPDATE SET
                                 name=EXCLUDED.name, address=EXCLUDED.address,
                                 latitude=EXCLUDED.latitude, longitude=EXCLUDED.longitude,
                                 description=EXCLUDED.description, updated_at=now()""",
                            (b["id_1c"], nz.text(b.get("code_1c")), nz.text(b.get("name")),
                             nz.text(b.get("address")), nz.num(b.get("latitude"), 6),
                             nz.num(b.get("longitude"), 6), nz.text(b.get("description"))))
        p = stamp / "agreements.json"
        if p.exists():
            for a in json.loads(p.read_text(encoding="utf-8")):
                if not isinstance(a, dict) or not a.get("id_1c"):
                    continue
                cur.execute("""INSERT INTO agreements (id_1c, code_1c, name) VALUES (%s, %s, %s)
                               ON CONFLICT (id_1c) DO UPDATE SET
                                 name=EXCLUDED.name, code_1c=EXCLUDED.code_1c, updated_at=now()""",
                            (a["id_1c"], nz.text(a.get("code_1c")), nz.text(a.get("name"))))
        p = stamp / "vehicle_brands.json"
        if p.exists():
            for v in json.loads(p.read_text(encoding="utf-8")):
                if isinstance(v, dict) and v.get("id_1c"):
                    cur.execute("""INSERT INTO vehicle_brands (id_1c, name) VALUES (%s, %s)
                                   ON CONFLICT (id_1c) DO UPDATE SET name=EXCLUDED.name, updated_at=now()""",
                                (v["id_1c"], nz.text(v.get("name"))))
        p = stamp / "nomenclature_groups.json"
        if p.exists():
            for g in json.loads(p.read_text(encoding="utf-8")):
                if not isinstance(g, dict) or not g.get("id_1c"):
                    continue
                cur.execute("""INSERT INTO nomenclature_groups (id_1c, code_1c, name, manufacturing_points, is_deleted)
                               VALUES (%s,%s,%s,%s,%s)
                               ON CONFLICT (id_1c) DO UPDATE SET
                                 code_1c=EXCLUDED.code_1c, name=EXCLUDED.name,
                                 manufacturing_points=EXCLUDED.manufacturing_points,
                                 is_deleted=EXCLUDED.is_deleted, updated_at=now()""",
                            (g["id_1c"], nz.text(g.get("code_1c")), nz.text(g.get("name")),
                             nz.jdump(g.get("manufacturing_points")), bool(g.get("deletion_mark"))))
    conn.commit()
    log.info("DICTS: %s", "ОК" if ok else "частично")
    return ok


# ── Главная ──────────────────────────────────────────────────────────────────

def main() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s",
                        datefmt="%H:%M:%S")
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    force = "--force" in sys.argv
    days = INCREMENT_DAYS
    for arg in sys.argv[2:]:
        if arg.startswith("--days="):
            days = int(arg.split("=", 1)[1])

    stamp = stamp_dir()
    conn = db.connect()
    db.ensure_schema(conn)
    try:
        t0 = time.time()
        is_sunday = today_msk().weekday() == 6  # 6 = вс (python-пн=0)
        if what in ("all", "dicts") and (is_sunday or force):
            sync_dicts(conn, stamp)
        if what in ("all", "orders"):
            sync_orders(conn, days=days, stamp=stamp)
        if what in ("all", "remnants"):
            sync_remnants(conn, stamp)
        if what in ("all", "prices") and (is_sunday or force):
            sync_prices(conn, stamp)
        log.info("DAILY-SYNC '%s' done за %.0fs", what, time.time() - t0)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
