"""Заказы-зона веб-слоя: список-заказов, досье-заказа, глобальный-поиск, CSV-экспорт.

Фаза 5 рефакторинга (docs/REFACTOR_PLAN.md): чистое перемещение из web.py, логика без изменений
(CSV-стриминг export/orders.csv — как есть, другой-стриминг-не-используем; Фаза 6: алиасы-импорты
_io/_csv возвращены к обычным io/csv). Регистрируется в web.py через include_router — пути/параметры
дословно как были.
"""
from __future__ import annotations

import io
import csv

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from web_common import q, q1

router = APIRouter()


@router.get("/api/orders")
def orders_list(qstr: str = Query("", alias="q"), status: str = "", since: str = "", till: str = "",
          limit: int = 50, offset: int = 0):
    """Страничный список заказов: фильтры по тексту/статусу/датам. Пагинация = стандартные limit/offset."""
    limit = max(1, min(200, limit))
    where = ["order_date IS NOT NULL"]; args: list = []
    if qstr:
        where.append("(number ILIKE %s OR contractor_name ILIKE %s OR id_1c ILIKE %s)")
        like = f"%{qstr}%"; args += [like, like, like]
    if status:
        where.append("order_status = %s"); args.append(status)
    if since:
        where.append("order_date >= %s"); args.append(since)
    if till:
        where.append("order_date < %s::date + interval '1 day'"); args.append(till)
    W = " AND ".join(where)
    total = q1(f"SELECT COUNT(*)::int AS c FROM orders WHERE {W}", tuple(args))["c"]
    rows = q(f"""
        SELECT id, order_id, number, order_date, order_status, contractor_name, branch_name, sum
        FROM orders WHERE {W}
        ORDER BY order_date DESC LIMIT %s OFFSET %s
    """, tuple(args + [limit, offset]))
    return {"items": rows, "total": total, "limit": limit, "offset": offset}


@router.get("/api/order/{order_id}/full")
def order_full(order_id: int):
    """Досье заказа: шапка + позиции + demand + shipments + sales + статус-история."""
    head = q1("""
        SELECT id, order_id, number, order_date, ordered_date, planned_shipment_date, planned_delivery_date,
               shipment_date, order_status, payment_status, sale_status,
               contractor_id_1c, contractor_name, branch_name, agreement_name, demand_responsible,
               sum, weight, comment,
               demand_id, demand_status, demand_date, demand_sum, demand_delivery_cost, demand_delivery_type,
               demand_address, demand_is_delivery
        FROM orders WHERE order_id = %s
    """, (order_id,))
    if not head:
        raise HTTPException(404, "order not found")
    oid = head["id"]
    items = q("""
        SELECT kind, id_1c, code_1c, name, group_name, unit, quantity, price, discount_pct, discount_price, total
        FROM order_items WHERE orders_id = %s ORDER BY kind, id
    """, (oid,))
    demand_items = q("""
        SELECT kind, id_1c, name, quantity, price, discount_pct, discount_price, total
        FROM demand_items WHERE orders_id = %s ORDER BY kind, id
    """, (oid,))
    shipments = q("""
        SELECT shipment_number, state, driver_name, driver_phone, source, updated_at
        FROM shipments WHERE orders_id = %s ORDER BY updated_at DESC
    """, (oid,))
    sales = q("""
        SELECT number, sales_date, ware_sum, service_sum, total_sum, posted, deletion_mark, subcontractor, kind
        FROM sales WHERE orders_id = %s AND deletion_mark = false ORDER BY sales_date DESC NULLS LAST
    """, (oid,))
    status_hist = q("""
        SELECT snapshot_date, order_status, payment_status, sale_status
        FROM order_status_history WHERE orders_id = %s ORDER BY snapshot_date
    """, (oid,))
    return {"head": head, "items": items, "demand_items": demand_items,
            "shipments": shipments, "sales": sales, "status_history": status_hist}


@router.get("/api/search_all")
def search_all(qstr: str = Query("", alias="q"), limit: int = 5):
    """Глобальный поиск: заказы (номер/контрагент) + товары (название) разом."""
    like = f"%{qstr}%"; lim = max(3, min(10, limit))
    if len(qstr) < 2:
        return {"orders": [], "items": []}
    orders = q("""
        SELECT order_id, number, order_date, order_status, contractor_name, sum
        FROM orders
        WHERE number ILIKE %s OR contractor_name ILIKE %s
        ORDER BY order_date DESC LIMIT %s
    """, (like, like, lim))
    items = q("""
        SELECT id_1c, full_name, color, thickness
        FROM nomenclature_full
        WHERE full_name ILIKE %s ORDER BY full_name LIMIT %s
    """, (like, lim))
    return {"orders": orders, "items": items}


@router.get("/api/export/orders.csv")
def export_orders(qstr: str = Query("", alias="q"), status: str = "", days: int = 0, date_from: str = "", date_to: str = ""):
    """CSV текущего фильтра заказов (до 5000 строк, {})."""
    like = f"%{qstr}%" if qstr else "%"
    wh = ["(number ILIKE %s OR contractor_name ILIKE %s)"]
    args: list = [like, like]
    if status:
        wh.append("order_status = %s"); args.append(status)
    if days:
        wh.append("order_date >= now() - (%s || ' days')::interval"); args.append(str(days))
    if date_from:
        wh.append("order_date >= %s"); args.append(date_from)
    if date_to:
        wh.append("order_date < %s::date + interval '1 day'"); args.append(date_to)
    rows = q("SELECT order_id, number, order_date, order_status, shipment_date, contractor_name, sum FROM orders WHERE " + " AND ".join(wh) + " ORDER BY order_date DESC LIMIT 5000", tuple(args))
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["id", "номер", "дата", "статус", "отгрузка", "контрагент", "сумма_заказа"])
    for r in rows:
        w.writerow([r["order_id"], r["number"], r["order_date"], r["order_status"], r["shipment_date"], r["contractor_name"], r["sum"]])
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv; charset=cp1251",
        headers={"Content-Disposition": "attachment; filename=orders.csv"})
