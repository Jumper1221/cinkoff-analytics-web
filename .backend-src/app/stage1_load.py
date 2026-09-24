"""Заливка сырых снапшотов (data/snapshots/initial-*) в Postgres.

Порядок: справочники → заказы → детали(пачками) → позиции/реализации/отгрузки.
Запускается ПОСЛЕ stage0_fetch.py. Идемпотентно: можно гнать повторно.

Запуск:  python -u stage1_load.py            # всё
         python -u stage1_load.py details 2  # только детали-пачки 0..1 (тест)
"""
from __future__ import annotations

import gzip
import json
import os
import sys
import time
from datetime import date, datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import psycopg2
import psycopg2.extras

import config
import db
import normalize as nz
import store

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "snapshots", "initial-2026-09-23"))


def _load(name):
    p = os.path.join(ROOT, name)
    if not os.path.exists(p):
        return None
    if name.endswith(".json.gz"):
        with gzip.open(p, "rt", encoding="utf-8") as f:
            return json.load(f)
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def _conn():
    conn = db.connect()
    db.ensure_schema(conn)
    return conn


# ── Справочники ──────────────────────────────────────────────────────────────

def load_branches(conn):
    rows = _load("branches.json") or []
    with conn.cursor() as cur:
        for b in rows:
            if not isinstance(b, dict) or not b.get("id_1c"):
                continue
            cur.execute(
                """INSERT INTO branches (id_1c, code_1c, name, address, latitude, longitude, description)
                   VALUES (%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (id_1c) DO UPDATE SET
                     name=EXCLUDED.name, address=EXCLUDED.address,
                     latitude=EXCLUDED.latitude, longitude=EXCLUDED.longitude,
                     description=EXCLUDED.description, updated_at=now()""",
                (b["id_1c"], nz.text(b.get("code_1c")), nz.text(b.get("name")),
                 nz.text(b.get("address")), nz.num(b.get("latitude"), 6),
                 nz.num(b.get("longitude"), 6), nz.text(b.get("description"))))
    conn.commit()
    print(f"branches: {len(rows)}")


def load_agreements(conn):
    rows = _load("agreements.json") or []
    with conn.cursor() as cur:
        for a in rows:
            if not isinstance(a, dict) or not a.get("id_1c"):
                continue
            cur.execute(
                """INSERT INTO agreements (id_1c, code_1c, name) VALUES (%s, %s, %s)
                   ON CONFLICT (id_1c) DO UPDATE SET
                     name=EXCLUDED.name, code_1c=EXCLUDED.code_1c, updated_at=now()""",
                (a["id_1c"], nz.text(a.get("code_1c")), nz.text(a.get("name"))))
    conn.commit()
    print(f"agreements: {len(rows)}")


def load_vehicle_brands(conn):
    rows = _load("vehicle_brands.json") or []
    with conn.cursor() as cur:
        for v in rows:
            if isinstance(v, dict) and v.get("id_1c"):
                cur.execute(
                    """INSERT INTO vehicle_brands (id_1c, name) VALUES (%s, %s)
                       ON CONFLICT (id_1c) DO UPDATE SET name=EXCLUDED.name, updated_at=now()""",
                    (v["id_1c"], nz.text(v.get("name"))))
    conn.commit()
    print(f"vehicle_brands: {len(rows)}")


def load_nomenclature_groups(conn):
    rows = _load("nomenclature_groups.json") or []
    n = 0
    with conn.cursor() as cur:
        for g in rows:
            if not isinstance(g, dict) or not g.get("id_1c"):
                continue
            cur.execute(
                """INSERT INTO nomenclature_groups (id_1c, code_1c, name, manufacturing_points, is_deleted)
                   VALUES (%s,%s,%s,%s,%s)
                   ON CONFLICT (id_1c) DO UPDATE SET
                     code_1c=EXCLUDED.code_1c, name=EXCLUDED.name,
                     manufacturing_points=EXCLUDED.manufacturing_points,
                     is_deleted=EXCLUDED.is_deleted, updated_at=now()""",
                (g["id_1c"], nz.text(g.get("code_1c")), nz.text(g.get("name")),
                 nz.jdump(g.get("manufacturing_points")),
                 bool(g.get("deletion_mark"))))
            n += 1
    conn.commit()
    print(f"nomenclature_groups: {n}")


def load_nomenclature_full(conn):
    rows = _load("nomenclatures_all.json.gz") or []
    print(f"nomenclature_full: вставка {len(rows)} записей...")
    # groups: id->name для денормализации
    with conn.cursor() as cur:
        cur.execute("SELECT id_1c, name FROM nomenclature_groups")
        gnames = dict(cur.fetchall())
    def upsert_batch(batch):
        with conn.cursor() as cur:
            for it in rows_batch:
                if not isinstance(it, dict) or not it.get("id_1c"):
                    continue
                gid = nz.text(it.get("nomenclature_group_id"))
                qu = it.get("quantity_unit") or {}
                qu_name = qu.get("name") if isinstance(qu, dict) else nz.text(qu)
                su = it.get("size_unit")
                au = it.get("amount_unit")
                if isinstance(su, dict):
                    su = (su or {}).get("name")
                if isinstance(au, dict):
                    au = (au or {}).get("name")
                cur.execute(
                    """INSERT INTO nomenclature_full (id_1c, code_1c, full_name, kind, group_id_1c,
                           group_name, color, surface, thickness, foil, weight, tnved,
                           quantity_unit, size_unit, amount_unit, raw)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT (id_1c) DO UPDATE SET
                         code_1c=COALESCE(EXCLUDED.code_1c, nomenclature_full.code_1c),
                         full_name=COALESCE(EXCLUDED.full_name, nomenclature_full.full_name),
                         kind=COALESCE(EXCLUDED.kind, nomenclature_full.kind),
                         group_id_1c=COALESCE(EXCLUDED.group_id_1c, nomenclature_full.group_id_1c),
                         group_name=COALESCE(EXCLUDED.group_name, nomenclature_full.group_name),
                         color=COALESCE(EXCLUDED.color, nomenclature_full.color),
                         surface=COALESCE(EXCLUDED.surface, nomenclature_full.surface),
                         thickness=COALESCE(EXCLUDED.thickness, nomenclature_full.thickness),
                         foil=COALESCE(EXCLUDED.foil, nomenclature_full.foil),
                         weight=COALESCE(EXCLUDED.weight, nomenclature_full.weight),
                         tnved=COALESCE(EXCLUDED.tnved, nomenclature_full.tnved),
                         quantity_unit=COALESCE(EXCLUDED.quantity_unit, nomenclature_full.quantity_unit),
                         size_unit=COALESCE(EXCLUDED.size_unit, nomenclature_full.size_unit),
                         amount_unit=COALESCE(EXCLUDED.amount_unit, nomenclature_full.amount_unit),
                         last_seen=CURRENT_DATE, raw=EXCLUDED.raw""",
                    (it["id_1c"], nz.text(it.get("code_1c")), nz.text(it.get("full_name")),
                     nz.text(it.get("nomenclature_kind")), gid,
                     gnames.get(gid),
                     nz.text(it.get("color")), nz.text(it.get("surface")),
                     nz.text(it.get("thickness")), nz.text(it.get("foil")),
                     nz.num(it.get("weight"), 3), nz.text(it.get("tnved")),
                     (qu_name if isinstance(qu, dict) else qu) and (qu.get("name") if isinstance(qu, dict) else qu),
                     (it.get("size_unit") or {}).get("name") if isinstance(it.get("size_unit"), dict) else su,
                     (it.get("amount_unit") or {}).get("name") if isinstance(it.get("amount_unit"), dict) else nz.text(it.get("amount_unit")),
                     nz.jdump(it)))
    t0 = time.time()
    # батчами по 5000 (231k одним execute_values слишком жирно для нашего jemalloc-_less окружения)
    B = 5000
    total = 0
    for i in range(0, len(rows), 5000):
        rows_batch = rows[i:i+5000]
        with conn.cursor() as cur:
            psycopg2.extras.execute_values(cur, """
                INSERT INTO nomenclature_full (id_1c, code_1c, full_name, kind, group_id_1c,
                       group_name, color, surface, thickness, foil, weight, tnved,
                       quantity_unit, size_unit, amount_unit, raw)
                VALUES %s
                ON CONFLICT (id_1c) DO UPDATE SET
                  code_1c=COALESCE(EXCLUDED.code_1c, nomenclature_full.code_1c),
                  full_name=COALESCE(EXCLUDED.full_name, nomenclature_full.full_name),
                  kind=COALESCE(EXCLUDED.kind, nomenclature_full.kind),
                  group_id_1c=COALESCE(EXCLUDED.group_id_1c, nomenclature_full.group_id_1c),
                  group_name=COALESCE(EXCLUDED.group_name, nomenclature_full.group_name),
                  color=COALESCE(EXCLUDED.color, nomenclature_full.color),
                  surface=COALESCE(EXCLUDED.surface, nomenclature_full.surface),
                  thickness=COALESCE(EXCLUDED.thickness, nomenclature_full.thickness),
                  foil=COALESCE(EXCLUDED.foil, nomenclature_full.foil),
                  weight=COALESCE(EXCLUDED.weight, nomenclature_full.weight),
                  tnved=COALESCE(EXCLUDED.tnved, nomenclature_full.tnved),
                  quantity_unit=COALESCE(EXCLUDED.quantity_unit, nomenclature_full.quantity_unit),
                  size_unit=COALESCE(EXCLUDED.size_unit, nomenclature_full.size_unit),
                  amount_unit=COALESCE(EXCLUDED.amount_unit, nomenclature_full.amount_unit),
                  last_seen=CURRENT_DATE""", [
                    (r.get("id_1c"), nz.text(r.get("code_1c")), nz.text(r.get("full_name")),
                     nz.text(r.get("nomenclature_kind")), nz.text(r.get("nomenclature_group_id")),
                     gnames.get(r.get("nomenclature_group_id")),
                     nz.text(r.get("color")), nz.text(r.get("surface")),
                     nz.text(r.get("thickness")), nz.text(r.get("foil")),
                     nz.num(r.get("weight"), 3), nz.text(r.get("tnved")),
                     (r.get("quantity_unit") or {}).get("name") if isinstance(r.get("quantity_unit"), dict) else nz.text(r.get("quantity_unit")),
                     (r.get("size_unit") or {}).get("name") if isinstance(r.get("size_unit"), dict) else nz.text(r.get("size_unit")),
                     (r.get("amount_unit") or {}).get("name") if isinstance(r.get("amount_unit"), dict) else nz.text(r.get("amount_unit")),
                     nz.jdump(r))
                    for r in rows_batch if isinstance(r, dict) and r.get("id_1c")
                ], page_size=500)
        conn.commit()
        total += len(rows_batch)
        print(f"  nomenclature_full: {total}/{len(rows)} ({time.time()-t0:.0f}s)")
    print(f"nomenclature_full: ГОТОВО {total} за {time.time()-t0:.0f}s")


def load_remnants(conn):
    """12 пачек remnants_*.json.gz -> remnants_snapshots.

    Строка: {nomenclature_id, remnants_metall: {storage: qty}, remnants_goods: {storage: qty},
             delivery_time: {storage: ISO-дата}}
    kind: metall | goods | delivery (для delivery: qty=0, delivery_date=дата прихода)
    """
    import gzip as _gz
    ddir = os.path.join(ROOT, "remnants")
    files = sorted(f for f in os.listdir(ddir) if f.endswith(".json.gz")) if os.path.isdir(ddir) else []
    if not files:
        print("remnants: нет файлов"); return
    today = date.today()
    total = 0
    t0 = time.time()
    cur = conn.cursor()
    for fn in files:
        with _gz.open(os.path.join(ddir, fn), "rt", encoding="utf-8") as f:
            rows = json.load(f)
        batch = []
        for it in rows:
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
                ddate = None
                if isinstance(dstr, str) and len(dstr) >= 10:
                    ddate = dstr[:10]
                batch.append((nid, storage_id, "delivery", 0, ddate, today))
        if not batch:
            continue
        psycopg2.extras.execute_values(cur, """
            INSERT INTO remnants_snapshots (nomenclature_id, storage_id, kind, qty, delivery_date, snapshot_date)
            VALUES %s
            ON CONFLICT (nomenclature_id, storage_id, kind, snapshot_date) DO NOTHING""",
            batch, page_size=1000)
        conn.commit()
        total += len(batch)
    cur.close()
    print(f"remnants_snapshots: {total} строк за {time.time()-t0:.0f}s (snapshot {today})")


def load_prices_v2(conn):
    """prices/<dir prices__{branch}__{agreement}/prices_*_NNN.json.gz -> prices_history.

    В записях НЕТ branch/agreement — берём из имени папки через справочники.
    """
    ddir = os.path.join(ROOT, "prices")
    if not os.path.isdir(ddir):
        print("prices: нет"); return
    branches = {b["id_1c"]: (b.get("name") or "") for b in (_load("branches.json") or []) if isinstance(b, dict)}
    agreements = {a["id_1c"]: (a.get("name") or "") for a in (_load("agreements.json") or []) if isinstance(a, dict)}

    def b2n(bid): return (branches.get(bid) or bid[:8]).replace("/", "-").replace(" ", "_")
    def a2n(aid): return (agreements.get(aid) or aid[:8]).split(";")[0].strip().replace(" ", "_")

    # имя папки -> (bid, aid): пробуем все пары
    pair_by_dir = {}
    for bid in branches:
        for aid in agreements:
            pair_by_dir[f"prices__{b2n(bid)}__{a2n(aid)}"] = (bid, aid)

    cur = conn.cursor()
    total = 0
    t0 = time.time()
    for dname in sorted(os.listdir(ddir)):
        dd2 = os.path.join(ddir, dname)
        if not os.path.isdir(dd2):
            continue
        pair = pair_by_dir.get(dname)
        if not pair:
            # имя могло обрезаться при сохранении (b[:20]) — ищем префиксное совпадение
            for pref, p in pair_by_dir.items():
                if dname.startswith(pref[:min(len(pref), len(dname))]) or pref.startswith(dname):
                    pair = p; break
        if not pair:
            print(f"  ! папка без пары: {dname}")
            continue
        bid, aid = pair
        for fn in sorted(f2 for f2 in os.listdir(dd2) if f2.endswith(".json.gz")):
            with gzip.open(os.path.join(dd2, fn), "rb") as f:
                rows = json.load(f)
            batch = [(it.get("nomenclature_id"), bid, aid,
                      nz.num(it.get("price")), nz.num(it.get("discount")),
                      nz.num(it.get("discountPrice")), nz.dt(it.get("version_date")))
                     for it in rows if isinstance(it, dict) and it.get("nomenclature_id")]
            if not batch:
                continue
            psycopg2.extras.execute_values(cur, """
                INSERT INTO prices_history (nomenclature_id, branch_id_1c, agreement_id_1c,
                                            price, discount_pct, discount_price, version_date)
                VALUES %s
                ON CONFLICT (nomenclature_id, branch_id_1c, agreement_id_1c, price, discount_pct, discount_price)
                DO UPDATE SET last_seen=CURRENT_DATE, version_date=EXCLUDED.version_date""", batch, page_size=1000)
            conn.commit()
            total += len(batch)
        print(f"  prices {dname[7:40]}: итого {total} ({time.time()-t0:.0f}s)")
    cur.close()
    print(f"PRICES: {total} строк за {time.time()-t0:.0f}s")


def load_files_and_misc(conn):
    """vehicle_brands уже; certificates + pim -> JSON-дампы (info); files-таблица заполнится после details."""
    rows = _load("certificates.json.gz") or []
    if rows:
        cur = conn.cursor()
        for it in rows:
            if isinstance(it, dict) and it.get("nomenclature_id") and it.get("link"):
                cur.execute("""INSERT INTO files (nomenclature_id, file_type, url)
                               VALUES (%s, %s, %s)
                               ON CONFLICT (nomenclature_id, url) DO UPDATE SET checked_at=CURRENT_DATE""",
                            (it["nomenclature_id"], nz.text(it.get("name")), it["link"]))
        conn.commit()
        print(f"files(certificates): {len(rows)}")


def load_details(conn, only_part=None):
    """18 пачек details_*.json.gz: для каждой записи — store.apply_detail + sales + shipment_processes.

    ВАЖНО: order_id в detail НЕ обязателен — orders уже есть после шага "orders" (из списка),
    иначе создаём: id берём из _order_id.
    """
    import concurrent.futures  # noqa
    ddir = os.path.join(ROOT, "details")
    if not os.path.isdir(ddir):
        print("details: нет"); return
    files = sorted(f for f in os.listdir(ddir) if f.endswith(".json.gz"))
    # ограничение по argv[2] (для теста: 'details 2' = первые 2 пачки)
    lim = None
    if len(sys.argv) > 2:
        lim = int(sys.argv[2])
    if lim:
        files = files[:lim]
    t0 = time.time()
    n_upd = n_sales = n_ship = 0
    cur = conn.cursor()
    for fi, fn in enumerate(files):
        with gzip.open(os.path.join(ddir, fn), "rb") as f:
            details = json.load(f)
        for key, d in details.items():
            if not isinstance(d, dict):
                continue
            oid_ext = d.get("_order_id") or int(key)
            # (1) найти/создать заказ: 90% уже есть (orders-шаг), 10% — только из деталей
            with conn.cursor() as c2:
                c2.execute("SELECT id FROM orders WHERE order_id = %s", (oid_ext,))
                row = c2.fetchone()
            orders_id = row[0] if row else store.upsert_order(conn, store.build_order_payload(d, detail=d, source="stage0-detail"))
            # (2) основная часть: поля + позиции + demand + справочники
            counts = store.apply_detail(conn, orders_id, d, source="stage0")
            # (3) sales + sales_correct (apply_detail их не пишет)
            for kind, key2 in (("sale", "sales"), ("correction", "sales_correct")):
                for sl in (d.get(key2) or []):
                    if not isinstance(sl, dict):
                        continue
                    cur.execute("""INSERT INTO sales (orders_id, id_1c, number, sales_date, ware_sum,
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
                    n_sales += 1
            # (4) shipment_processes -> shipments (source='detail')
            if d.get("shipment_processes"):
                n_ship += store.upsert_shipments(conn, orders_id, [
                    {"shipmentNumber": sp.get("registerNumber"),
                     "shipmentState": sp.get("vehicleState"),
                     "driverName": sp.get("driver"),
                     "driverPhones": sp.get("driverTelephones")}
                    for sp in d["shipment_processes"] if isinstance(sp, dict)
                ], source="detail") or 0
            # (5) detail_hash/TTL: apply_detail уже проставил? Проверим хвост apply_detail... хвост добавлю тут:
            cur.execute("UPDATE orders SET detail_hash=%s, detail_fetched_at=now() WHERE id=%s",
                        (nz.detail_fingerprint(d), orders_id))
            n_upd += 1
            if n_upd % 1000 == 0:
                conn.commit()
                print(f"  … {n_upd} деталей (файл {fi+1}/{len(files)}, {time.time()-t0:.0f}s)")
        conn.commit()
        print(f"  файл {fi+1}/{len(files)}: +{len(details)} (итого {n_upd} заказов, {time.time()-t0:.0f}s)")
    cur.close()
    print(f"DETAILS: заказов={n_upd}, sales={n_sales}, shipments+={n_ship}, {time.time()-t0:.0f}s")


WHAT = "all"

def main():
    global WHAT
    WHAT = sys.argv[1] if len(sys.argv) > 1 else "all"
    conn = _conn()
    try:
        t0 = time.time()
        # справочники
        if WHAT in ("all", "dicts"):
            load_branches(conn)
            load_agreements(conn)
            load_vehicle_brands(conn)
            # nomenclature_groups (921) — до nomenclature_full
            groups = _load("nomenclature_groups.json") or []
            with conn.cursor() as cur:
                for g in groups:
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
            print(f"nomenclature_groups: {len(groups)}")
        if WHAT in ("all", "nomenclature"):
            load_nomenclature_full(conn)
        if WHAT in ("all", "remnants"):
            load_remnants(conn)
        if WHAT in ("all", "orders"):
            # шапки 8706 -> orders (COALESCE-безопасно)
            rows = _load("orders_all.json.gz") or []
            n = 0
            for row in rows:
                if not isinstance(row, dict):
                    continue
                try:
                    oid = store.upsert_order(conn, store.build_order_payload(row, source="stage0-list"))
                    if row.get("shipment_info"):
                        store.upsert_shipments(conn, oid, row["shipment_info"], source="list")
                    store.snapshot_order(conn, oid)
                    n += 1
                except Exception as e:
                    conn.rollback()
                    print("  ! заказ", row.get("order_id"), ":", str(e)[:100])
            conn.commit()
            print(f"orders: {n} upsert-ов (история 2019→)")
        if WHAT in ("all", "details"):
            load_details(conn)
        if WHAT in ("all", "prices"):
            load_prices_v2(conn)
        if WHAT in ("all", "misc"):
            load_files_and_misc(conn)
        print(f"\nSTAGE1 DONE за {time.time()-t0:.0f}s")
    finally:
        conn.close()


if __name__ == "__main__":
    import store  # for build_order_payload/upsert_order inside load_details
    main()
