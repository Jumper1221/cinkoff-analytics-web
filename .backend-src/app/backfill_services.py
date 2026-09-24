"""Одноразовая-задача: перезалить услуги из raw_detail (в-БД) по-фиксу-маппинга Serv-полей.

До-фикса: replace_items-писал-услуги-с-NULL-в-quantity/price/total (имена-полей-не-совпадали).
Сырьё-никогда-не-терялось: raw_detail (jsonb) в orders.Хранит-полные-детали.
После-фикса: new-детали-заливаются-правильно; старые-—-этим-скриптом-из-raw_detail.

Запуск:  python -u backfill_services.py            # да-нет-подтверждение-не-спрашиваю: идемпотентно
"""
from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import store
import db


def main() -> None:
    conn = db.connect()
    db.ensure_schema(conn)
    t0 = time.time()
    n_done = n_skip = 0
    with conn.cursor() as cur:  # заказов-с-услугами-1508 — память-не-проблема
        cur.execute("""SELECT id, raw_detail FROM orders
                       WHERE raw_detail IS NOT NULL AND (raw_detail->'order_services')::text <> '[]'::text""")
        rows = cur.fetchall()
    for orders_id, raw in rows:
            try:
                detail = raw if isinstance(raw, dict) else json.loads(raw)
            except (TypeError, ValueError):
                n_skip += 1
                continue
            services = detail.get("order_services") or []
            if not services:
                n_skip += 1
                continue
            store.replace_items(conn, orders_id, "order_items", "service", services)
            n_done += 1
            if n_done % 1000 == 0:
                conn.commit()
                print(f"  … {n_done} заказов ({time.time()-t0:.0f}s)")
    conn.commit()
    # контроль: сколько-услуг-теперь-с-данными
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FILTER (WHERE quantity IS NOT NULL), COUNT(*) FROM order_items WHERE kind='service'")
        filled, total = cur.fetchone()
    print(f"SERVICES-BACKFILL: заказов-обработано {n_done}, пропущено {n_skip}; "
          f"услуг-с-данными {filled}/{total} за {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
