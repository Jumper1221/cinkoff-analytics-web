"""Синхронизация: список -> orders (+снапшот) -> детали для новых/изменённых.

Режимы:
- sync()          — ежедневный: список + детали новых/изменённых + снапшот статусов.
- enrich(limit)   — догружает детали заказам, у которых их ещё нет (старые, вне списка).
- backfill(dir)   — разовая заливка исторических дампов (справочник + снапшоты по дате дампа).
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import psycopg2

import config
import gl_api
import normalize as nz
import store

log = logging.getLogger(__name__)


def _sync_log_start(conn, mode: str) -> int:
    return store.start_sync(conn, mode)


def _sync_log_finish(conn, sid: int, **counts: Any) -> None:
    counts["sync_id"] = sid
    store.finish_sync(conn, sid, **counts)


def _new_changed_orders(conn, rows: list[dict[str, Any]]) -> list[int]:
    """orders.id тех, у кого list_sig отличается (или которых ещё нет)."""
    ids: list[int] = []
    with conn.cursor() as cur:
        for row in rows:
            sig = nz.list_sig(row)
            cur.execute(
                "SELECT id, list_sig FROM orders WHERE order_id = %s AND ((id_1c IS NOT NULL AND id_1c = %s) OR (id_1c IS NULL AND %s IS NULL))",
                (nz.num(row.get("order_id"), 0), nz.text(row.get("order_id_1c")), nz.text(row.get("order_id_1c"))))
            found = cur.fetchone()
            if not found or found[1] != sig:
                ids.append(found[0] if found else -1)  # -1:创建 после upsert
    return ids


def sync(conn, api_key: str, *, with_details: bool = True) -> dict[str, Any]:
    """Один полный цикл. Возвращает counts для sync_log."""
    sid = _sync_log_start(conn, "daily")
    counts: dict[str, Any] = dict(orders_seen=0, details_fetched=0, details_skipped=0,
                                  items_upserted=0, errors=0, error_detail=None)
    try:
        rows = gl_api.fetch_order_list(api_key)
        counts["orders_seen"] = len(rows)
        log.info("список: %d заказов", len(rows))

        today_orders_ids: list[int] = []
        for row in rows:
            # 1. UPSERT самого заказа (list-поля)
            payload = store.build_order_payload(row, source="api")
            orders_id = store.upsert_order(conn, payload)

            # 2. отгрузки из списка (shipment_info)
            if row.get("shipment_info"):
                store.upsert_shipments(conn, orders_id, row["shipment_info"], source="list")

            # 3. ежедневный срез (только не-терминальные статусы)
            store.snapshot_order(conn, orders_id)
            today_orders_ids.append(orders_id)

        conn.commit()  # фиксируем список+снапшоты до тяжелой детали-фазы

        # 4. детали: только новые/изменённые, ИЛИ не-терминальные и устаревшие
        if with_details:
            need: list[tuple[int, int]] = []  # (orders_id, order_id)
            seen: set[int] = set()
            with conn.cursor() as cur:
                # ТОЛЬКО заказы из текущего списка (id выше) — история догружается enrich-ом
                cur.execute("SELECT id, order_id, list_sig FROM orders WHERE order_id = ANY(%s)",
                            ([nz.num(r.get("order_id"), 0) for r in rows],))
                for (oid, ext_id, lsig) in cur.fetchall():
                    if oid in seen:
                        continue
                    seen.add(oid)
                    row = next((r for r in rows if nz.num(r.get("order_id"), 0) == ext_id), None)
                    if store.needs_detail(conn, oid, config.DETAILS_MAX_AGE_H,
                                          current_list_sig=(nz.list_sig(row) if row else None)):
                        need.append((oid, ext_id))
            if config.MAX_DETAILS_PER_RUN:
                need = need[:config.MAX_DETAILS_PER_RUN]
            counts["details_skipped"] = max(0, counts["orders_seen"] - len(need))

            for i, (orders_id, ext_id) in enumerate(need):
                try:
                    detail = gl_api.fetch_order_detail(api_key, ext_id)
                    res = store.apply_detail(conn, orders_id, detail, source="api")
                    counts["items_upserted"] += res.get("items", 0) + res.get("demand_items", 0)
                    counts["details_fetched"] += 1
                    with conn.cursor() as cur:
                        cur.execute("UPDATE orders SET detail_fetched_at = now() WHERE id = %s", (orders_id,))
                except (gl_api.ApiException, psycopg2.Error) as exc:
                    counts["errors"] += 1
                    counts["error_detail"] = f"order {ext_id}: {exc}"[:2000]
                    log.warning("деталь %s: %s", ext_id, exc)
                    conn.rollback()
                if (i + 1) % 20 == 0:
                    conn.commit()
                    log.info("детали: %d/%d", i + 1, len(need))
                time.sleep(0.15)  # вежливость к чужому API

        conn.commit()
        _sync_log_finish(conn, sid, **counts)
        log.info("sync done: %s", counts)
        return counts
    except Exception as exc:
        counts["errors"] = (counts.get("errors") or 0) + 1
        counts["error_detail"] = str(exc)[:2000]
        conn.rollback()
        _sync_log_finish(conn, sid, **counts)
        log.exception("sync failed")
        raise


def enrich(conn, api_key: str, limit: int) -> dict[str, Any]:
    """Догрузить детали заказам, у которых их ещё нет (исторические, вне списка)."""
    sid = _sync_log_start(conn, "enrich")
    counts: dict[str, Any] = dict(orders_seen=limit, details_fetched=0, details_skipped=0,
                                  items_upserted=0, errors=0, error_detail=None)
    try:
        todo = _fetch_needs(conn, limit)
        log.info("enrich: %d заказов ждут деталей", len(todo))
        for i, (orders_id, ext_id) in enumerate(todo):
            try:
                detail = gl_api.fetch_order_detail(api_key, ext_id)
                res = store.apply_detail(conn, orders_id, detail, source="api")
                counts["items_upserted"] += res.get("items", 0) + res.get("demand_items", 0)
                counts["details_fetched"] += 1
                with conn.cursor() as cur:
                    cur.execute("UPDATE orders SET detail_fetched_at = now() WHERE id = %s", (orders_id,))
            except (gl_api.ApiException, psycopg2.Error) as exc:
                counts["errors"] += 1
                counts["error_detail"] = f"order {ext_id}: {exc}"[:2000]
                conn.rollback()
            if (i + 1) % 20 == 0:
                conn.commit()
                log.info("enrich: %d/%d", i + 1, len(todo))
            time.sleep(0.15)
        conn.commit()
        _sync_log_finish(conn, sid, **counts)
        return counts
    except Exception as exc:
        counts["errors"] = 1
        counts["error_detail"] = str(exc)[:2000]
        conn.rollback()
        _sync_log_finish(conn, sid, **counts)
        raise


def _fetch_needs(conn, limit: int) -> list[tuple[int, int]]:
    with conn.cursor() as cur:
        cur.execute("""SELECT id, order_id FROM orders
                       WHERE detail_hash IS NULL AND order_id IS NOT NULL
                       ORDER BY order_date DESC NULLS LAST LIMIT %s""", (limit,))
        return cur.fetchall()


_DUMP_DATE = re.compile(r"Cinkoff_orders_(\d{4}-\d{2}-\d{2})_")

def backfill(conn, dumps_dir: str) -> dict[str, Any]:
    """Заливка исторических дампов: заказы + отгрузки + снапшоты статусов ПО ДАТЕ ДАМПА.

    Дамп = список заказов без позиций; позиции подтянут потом enrich.
    Идемпотентно: повторный прогон не создаёт дублей (upsert + снапшоты ON CONFLICT).
    """
    sid = _sync_log_start(conn, "backfill")
    counts: dict[str, Any] = dict(orders_seen=0, details_fetched=0, details_skipped=0,
                                  items_upserted=0, errors=0, error_detail=None)
    files = sorted(Path(dumps_dir).glob("Cinkoff_orders_*.json"))
    log.info("backfill: %d файлов дампов", len(files))
    try:
        for f in files:
            m = _DUMP_DATE.search(f.name)
            if not m:
                continue
            snap_date = date.fromisoformat(m.group(1))
            try:
                rows = json.loads(f.read_text(encoding="utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                rows = json.loads(f.read_text(encoding="utf-16"))
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, dict):
                    continue
                counts["orders_seen"] += 1
                try:
                    orders_id = store.upsert_order(conn, store.build_order_payload(row, source=f"backfill:{f.name}"))
                    if row.get("shipment_info"):
                        store.upsert_shipments(conn, orders_id, row["shipment_info"], source="list")
                    # исторический срез: статус/сумма НА ДАТУ ДАМПА
                    _history_snapshot(conn, orders_id, snap_date, row)
                except psycopg2.Error as exc:
                    counts["errors"] += 1
                    counts["error_detail"] = f"{f.name}: {exc}"[:2000]
                    conn.rollback()
            conn.commit()
            log.info("backfill %s: +залито", f.name)
        _sync_log_finish(conn, sid, **counts)
        return counts
    except Exception as exc:
        counts["errors"] = (counts.get("errors") or 0) + 1
        counts["error_detail"] = str(exc)[:2000]
        conn.rollback()
        _sync_log_finish(conn, sid, **counts)
        raise


def _history_snapshot(conn, orders_id: int, snap_date: date, row: dict[str, Any]) -> None:
    """Срез для исторического дампа: пишем статус/сумму КАК-ТО-ТОГДА (не терминальные)."""
    status = nz.text(row.get("order_status"))
    if status in config.SNAPSHOT_EXCLUDE_STATUSES:
        return
    with conn.cursor() as cur:
        cur.execute("""INSERT INTO order_status_history
                       (orders_id, snapshot_date, order_status, payment_status, sale_status, sum, weight)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (orders_id, snapshot_date) DO NOTHING""",
                    (orders_id, snap_date, status,
                     nz.text(row.get("order_payment_status")), nz.text(row.get("order_sale_status")),
                     nz.num(row.get("order_sum")), nz.num(row.get("order_weight"), 0)))
