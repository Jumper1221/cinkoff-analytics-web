"""Cinkoff Analytics API — read-only JSON API + статика SPA.

Запуск: python -u web.py  (0.0.0.0:8000, за nginx/traefik не нужен)
"""
from __future__ import annotations

import datetime
import os
import sys
from contextlib import contextmanager

import psycopg2
import psycopg2.extras
import io
_io = io
import csv
_csv = csv
from fastapi import FastAPI, HTTPException, Query
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

PG = dict(
    host=os.getenv("PG_HOST", "localhost"),
    port=int(os.getenv("PG_PORT", "5432")),
    dbname=os.getenv("PG_DB", "orders"),
    user=os.getenv("PG_USER", "orders"),
    password=os.getenv("PG_PASSWORD", "orders_password_change_me"),
    connect_timeout=5,
)


from psycopg2.pool import SimpleConnectionPool

_pool: SimpleConnectionPool | None = None


def _pool_get() -> SimpleConnectionPool:
    global _pool
    if _pool is None:
        _pool = SimpleConnectionPool(2, 10, **PG)
    return _pool


@contextmanager
def _cur():
    pool = _pool_get()
    conn = pool.getconn()
    try:
        conn.autocommit = True
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            yield cur
        # вернуть живое соединение в пул
        if conn.closed:
            pool.putconn(conn, close=True)
        else:
            conn.rollback()  # сброс транзакции-стейта
            pool.putconn(conn)
    except Exception:
        try:
            conn.rollback()
            pool.putconn(conn, close=conn.closed)
        except Exception:
            pool.putconn(conn, close=True)
        raise


def q(sql: str, args: tuple = ()) -> list[dict]:
    with _cur() as cur:
        cur.execute(sql, args)
        return [dict(r) for r in cur.fetchall()]


def q1(sql: str, args: tuple = ()):
    rows = q(sql, args)
    return rows[0] if rows else {}

from fastapi.middleware.gzip import GZipMiddleware

app = FastAPI(title="Cinkoff Analytics", docs_url=None, redoc=None, openapi_url=None)
app.add_middleware(GZipMiddleware, minimum_size=1024)


@app.middleware("http")
async def cache_control(request, call_next):
    resp = await call_next(request)
    p = request.url.path
    if p.startswith("/static/vendor"):
        resp.headers["Cache-Control"] = "public, max-age=86400, immutable"   # 1 сутки, они не меняются
    elif p.startswith("/static"):
        resp.headers["Cache-Control"] = "public, max-age=300"                # 5 минут — свой код
    elif p.startswith("/api/branches") or p.startswith("/api/remnants/dates"):
        resp.headers["Cache-Control"] = "public, max-age=600"                # справочники 10 мин
    return resp


def _jsoned(rows):
    import datetime, decimal
    def enc(o):
        if isinstance(o, (datetime.datetime, datetime.date)):
            return o.isoformat()
        if isinstance(o, decimal.Decimal):
            return float(o)
        return str(o)
    return JSONResponse(rows if isinstance(rows, list) else [rows], default=enc)


@app.get("/api/kpi")
def kpi():
    return q1("""
        SELECT
          (SELECT COUNT(*)::int FROM orders WHERE order_date::date = (now() AT TIME ZONE 'Europe/Moscow')::date) AS orders_today,
          (SELECT COUNT(*)::int FROM orders WHERE order_date >= now() - interval '30 days') AS orders_30d,
          (SELECT COALESCE(SUM(CASE WHEN order_status IN ('Машина отгружена', 'Отгружен') THEN COALESCE(sum,0) ELSE 0 END),0)::float8 FROM orders WHERE order_date >= now() - interval '30 days') AS sum_30d,
          (SELECT COUNT(*)::int FROM orders WHERE order_date >= now() - interval '30 days' AND order_status = 'Машина отгружена') AS shipped_30,
          (SELECT AVG(CASE WHEN order_status IN ('Машина отгружена', 'Отгружен') THEN COALESCE(sum,0) END)::float8 FROM orders WHERE order_date >= now() - interval '30 days') AS avg_30
    """)


@app.get("/api/years")
def years():
    return q("""
        SELECT EXTRACT(year FROM order_date)::int AS year,
               COUNT(*)::int AS cnt,
               SUM(CASE WHEN order_status IN ('Машина отгружена', 'Отгружен') THEN COALESCE(sum,0) ELSE 0 END)::float8 AS revenue,
               AVG(CASE WHEN order_status IN ('Машина отгружена', 'Отгружен') THEN COALESCE(sum,0) END)::float8 AS avg_check,
               COUNT(*) FILTER (WHERE order_status IN ('Машина отгружена', 'Отгружен'))::int AS done_cnt
        FROM orders WHERE order_date IS NOT NULL
        GROUP BY 1 ORDER BY 1
    """)


@app.get("/api/monthly")
def monthly(months: int = 24):
    months = max(3, min(60, months))
    return q(f"""
        SELECT EXTRACT(year FROM order_date)::int AS year,
               EXTRACT(month FROM order_date)::int AS month,
               COUNT(*)::int AS cnt,
               SUM(CASE WHEN order_status IN ('Машина отгружена', 'Отгружен') THEN COALESCE(sum,0) ELSE 0 END)::float8 AS total,
               COUNT(*) FILTER (WHERE order_status IN ('Машина отгружена', 'Отгружен'))::int AS done_cnt
        FROM orders WHERE order_date >= now() - interval '{months} months'
        GROUP BY 1,2 ORDER BY 1,2
    """)


@app.get("/api/top/contractors")
def top_contractors(limit: int = 10, days: int = 365):
    limit = max(1, min(50, limit))
    days = max(30, min(3650, days))
    return q(f"""
        SELECT contractor_name AS name, COUNT(*)::int AS orders,
               SUM(CASE WHEN order_status IN ('Машина отгружена', 'Отгружен') THEN COALESCE(sum,0) ELSE 0 END)::float8 AS revenue
        FROM orders
        WHERE contractor_name IS NOT NULL AND order_date >= now() - interval '{days} days'
        GROUP BY 1 ORDER BY 2 DESC LIMIT {limit}
    """)


@app.get("/api/top/items")
def top_items(limit: int = 10, days: int = 760):
    limit = max(1, min(50, limit))
    days = max(30, min(3650, days))
    return q(f"""
        SELECT i.name, SUM(i.quantity)::float8 AS units, SUM(COALESCE(i.total,0))::float8 AS revenue
        FROM order_items i
        JOIN orders o ON o.id = i.orders_id
        WHERE i.kind = 'nomenclature' AND o.order_date >= now() - interval '{days} days'
        GROUP BY 1 ORDER BY 3 DESC LIMIT {limit}
    """)


@app.get("/api/status_breakdown")
def status_breakdown(days: int = 365):
    days = max(30, min(3650, days))
    return q(f"""
        SELECT COALESCE(order_status, '—') AS status, COUNT(*)::int AS cnt
        FROM orders WHERE order_date >= now() - interval '{days} days'
        GROUP BY 1 ORDER BY 2 DESC
    """)


@app.get("/api/freshness")
def freshness():
    r = q1("SELECT MAX(order_date)::date AS last_order, COUNT(*)::int AS total, COUNT(*)::int AS total_orders FROM orders")
    # примечание:fresh.last_order/total, total_orders дублирует total для шаблона
    return r


@app.get("/api/orders")
def orders_list(qstr: str = Query("", alias="q"), status: str = "", since: str = "", till: str = "",
          page: int = 1, per: int = 50):
    """Страничный список заказов: фильтры по тексту/статусу/датам."""
    page = max(1, page); per = max(10, min(200, per))
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
    """, tuple(args + [per, (page - 1) * per]))
    return {"items": rows, "total": total, "page": page, "per": per}


@app.get("/api/catalog/search")
def catalog_search(s: str = Query(min_length=2, max_length=100), limit: int = 25):
    like = f"%{s}%"
    return q("""
        SELECT n.id_1c, n.full_name, n.color, n.thickness, n.surface, n.weight, n.group_name,
               (SELECT COUNT(DISTINCT p.branch_id_1c) FROM prices_history p WHERE p.nomenclature_id = n.id_1c) AS branches
        FROM nomenclature_full n
        WHERE n.full_name ILIKE %s
        ORDER BY n.full_name
        LIMIT %s
    """, (like, min(limit, 100)))


@app.get("/api/catalog/prices/{nom_id}")
def catalog_prices(nom_id: str):
    return q("""
        SELECT p.branch_id_1c, b.name AS branch, p.price, p.discount_pct, p.discount_price, p.version_date
        FROM prices_history p
        LEFT JOIN branches b ON b.id_1c = p.branch_id_1c
        WHERE p.nomenclature_id = %s
        ORDER BY p.discount_price DESC NULLS LAST
    """, (nom_id,))


@app.get("/api/catalog/price_history/{nom_id}")
def catalog_price_history(nom_id: str, branch: str = ""):
    if branch:
        return q("""
            SELECT version_date, branch_id_1c, b.name AS branch, price, discount_price
            FROM prices_history p LEFT JOIN branches b ON b.id_1c = p.branch_id_1c
            WHERE nomenclature_id = %s AND p.branch_id_1c = %s
            ORDER BY version_date
        """, (nom_id, branch))
    return q("""
        SELECT DISTINCT ON (version_date::date, branch_id_1c)
               version_date, branch_id_1c, b.name AS branch, price, discount_price
        FROM prices_history p LEFT JOIN branches b ON b.id_1c = p.branch_id_1c
        WHERE nomenclature_id = %s
        ORDER BY version_date::date, branch_id_1c, version_date DESC
        LIMIT 500
    """, (nom_id,))


@app.get("/api/remnants")
def remnants(kind: str = "metall", snap_date: str = "", limit: int = 100):
    """Без-даты = последний-снапшот (иначе-дубли товар×склад по-2+-датам)."""
    lim = max(1, min(500, limit))
    if not snap_date:
        row = q1("SELECT MAX(snapshot_date)::date AS d FROM remnants_snapshots WHERE kind = %s", (kind,))
        snap_date = (row["d"].isoformat() if row and row["d"] else "")
    d = f"AND snapshot_date = %s" if (snap_date) else ""
    args = [kind] + ([snap_date] if snap_date else [])
    return q(f"""
        SELECT r.nomenclature_id, n.name AS full_name,
               r.storage_id, COALESCE(b.name, r.storage_id) AS branch,
               r.qty, r.delivery_date, r.snapshot_date
        FROM remnants_snapshots r
        LEFT JOIN nomenclature n  ON n.id_1c = r.nomenclature_id
        LEFT JOIN branches b      ON b.id_1c = r.storage_id
        WHERE r.kind = %s {d}
        ORDER BY r.delivery_date ASC NULLS LAST, r.qty DESC
        LIMIT %s
    """, tuple(args + [lim]) if snap_date else (kind, lim))


@app.get("/api/remnants/dates")
def remnants_dates():
    r = q("SELECT DISTINCT snapshot_date::text AS d FROM remnants_snapshots ORDER BY 1 DESC LIMIT 30")
    return {"dates": [x["d"] for x in r]}




@app.get("/api/order/{order_id}/full")
def order_full(order_id: int):
    """Досье заказа: шапка + позиции + demand + shipments + sales + статус-история."""
    head = q1("""
        SELECT id, order_id, number, order_date, ordered_date, planned_shipment_date, planned_delivery_date,
               shipment_date, order_status, payment_status, sale_status,
               contractor_id_1c, contractor_name, branch_name, agreement_name,
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




@app.get("/api/compare")
def compare(period: str = "month", anchor: str = "", steps: int = 1):
    """Сравнить период с предыдущим: сколько заказов/сумма/средний.

    period=month: anchor=YYYY-MM (по умолчанию текущий), steps назад — возвращает [текущий, предыдущий, ...]
    """
    import calendar
    period = period if period in ("month", "quarter", "year") else "month"
    steps = max(1, min(5, steps))
    if not anchor:
        now = datetime.date.today()
        anchor = now.strftime("%Y-%m") if period == "month" else now.strftime("%Y") if period == "year" else f"{now.year}-Q{(now.month - 1) // 3 + 1}"
    out = []
    if period == "month":
        y, m = map(int, anchor.split("-"))
        for k in range(steps + 1):
            yy, mm = (y, m - k)
            while mm <= 0:
                mm += 12; yy -= 1
            first = f"{yy:04d}-{mm:02d}-01"
            last = f"{yy:04d}-{mm:02d}-{calendar.monthrange(yy, mm)[1]}"
            row = q1("""SELECT COUNT(*)::int AS orders, COALESCE(SUM(sum),0)::float8 AS revenue,
                              COALESCE(AVG(sum),0)::float8 AS avg_check,
                              COUNT(*) FILTER (WHERE order_status = 'Отменен')::int AS canceled
                       FROM orders WHERE order_date >= %s AND order_date < %s::date + interval '1 day'""",
                     (first, last))
            row.update(label=first[:7], kind="month")
            out.append(row)
    elif period == "year":
        y = int(anchor[:4])
        for k in range(steps + 1):
            yy = y - k
            row = q1("""SELECT COUNT(*)::int AS orders, COALESCE(SUM(sum),0)::float8 AS revenue,
                              COALESCE(AVG(sum),0)::float8 AS avg_check,
                              COUNT(*) FILTER (WHERE order_status = 'Отменен')::int AS canceled
                       FROM orders WHERE EXTRACT(year FROM order_date) = %s""", (yy,))
            row.update(label=str(yy), kind="year")
            out.append(row)
    else:  # quarter
        y, qn = anchor.split("-Q")
        y, qn = int(y), int(qn)
        for k in range(steps + 1):
            qq = qn - k
            yy = y
            while qq <= 0:
                qq += 4; yy -= 1
            first_m = (qq - 1) * 3 + 1
            last_m = first_m + 2
            first = f"{yy:04d}-{first_m:02d}-01"
            last = f"{yy:04d}-{last_m:02d}-{calendar.monthrange(yy, last_m)[1]}"
            row = q1("""SELECT COUNT(*)::int AS orders, COALESCE(SUM(sum),0)::float8 AS revenue,
                              COALESCE(AVG(sum),0)::float8 AS avg_check,
                              COUNT(*) FILTER (WHERE order_status = 'Отменен')::int AS canceled
                       FROM orders WHERE order_date >= %s AND order_date < %s::date + interval '1 day'""",
                     (first, last))
            row.update(label=f"{yy}-Q{qq}", kind="quarter")
            out.append(row)
    # дельты: каждая строка vs следующая (более ранний)
    res = []
    for i, r in enumerate(out):
        if i + 1 < len(out):
            prev = out[i + 1]
            r["prev_orders"] = prev["orders"]; r["prev_revenue"] = prev["revenue"]
            r["d_orders"] = r["orders"] - prev["orders"]
            r["d_revenue"] = round(r["revenue"] - prev["revenue"], 2)
            r["p_orders"] = round(100 * (r["orders"] - prev["orders"]) / prev["orders"], 1) if prev["orders"] else None
            r["p_revenue"] = round(100 * (r["revenue"] - prev["revenue"]) / prev["revenue"], 1) if prev["revenue"] else None
        res.append(r)
    return res




@app.get("/api/leadtime")
def leadtime(months: int = 12):
    """Скорость исполнения: медиана дней заказ→shipment_date по месяцам + % отмен."""
    months = max(3, min(60, months))
    return q(f"""
        WITH done AS (
          SELECT date_trunc('month', order_date) AS m,
                 EXTRACT(day FROM (shipment_date - order_date))::float8 AS days,
                 order_status
          FROM orders
          WHERE shipment_date IS NOT NULL AND order_date IS NOT NULL
            AND order_date >= now() - interval '{months} months'
        )
        SELECT to_char(m, 'YYYY-MM') AS label,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY days) AS median_days,
               percentile_cont(0.9) WITHIN GROUP (ORDER BY days) AS p90_days,
               COUNT(*)::int AS shipped
        FROM done GROUP BY 1 ORDER BY 1
    """)


@app.get("/api/cancel_rate")
def cancel_rate(months: int = 12):
    """% отмен по месяцам (по дате заказа)."""
    months = max(3, min(60, months))
    return q(f"""
        SELECT to_char(date_trunc('month', order_date), 'YYYY-MM') AS label,
               COUNT(*)::int AS orders,
               COUNT(*) FILTER (WHERE order_status = 'Отменен')::int AS canceled,
               ROUND(100.0 * COUNT(*) FILTER (WHERE order_status = 'Отменен') / COUNT(*), 1) AS pct
        FROM orders
        WHERE order_date >= now() - interval '{months} months'
        GROUP BY 1 ORDER BY 1
    """)


@app.get("/api/stale")
def stale(days: int = 14, limit: int = 50):
    """Незакрытые заказы старше N дней: статус-возраст, без отгрузки."""
    lim = max(5, min(200, limit))
    return q(f"""
        SELECT order_id, number, order_date, order_status, contractor_name, branch_name, sum,
               EXTRACT(day FROM (now() - order_date))::int AS age_days
        FROM orders
        WHERE order_date < now() - interval '{days} days'
          AND order_status NOT IN ('Машина отгружена', 'Отменен')
        ORDER BY order_date
        LIMIT {lim}
    """)




@app.get("/api/abc")
def abc(days: int = 365, cls: str = ""):
    """ABC-классы товаров по выручке: A=80% кумулятив, B=15%, C=5%. Требует 0.80/0.95/1.00 порогов."""
    lim = 400
    rows = q(f"""
        WITH rev AS (
          SELECT i.name, SUM(COALESCE(i.total,0))::float8 AS revenue, SUM(i.quantity)::float8 AS units
          FROM order_items i JOIN orders o ON o.id = i.orders_id
          WHERE i.kind='nomenclature' AND o.order_date >= now() - interval '{days} days'
          GROUP BY 1
        ), cum AS (
          SELECT name, revenue, units,
                 SUM(revenue) OVER (ORDER BY revenue DESC) AS cum_rev,
                 SUM(revenue) OVER () AS total_rev
          FROM rev
        )
        SELECT name, revenue, units,
               ROUND((100.0 * revenue / total_rev)::numeric, 2) AS share_pct,
               ROUND((100.0 * cum_rev / total_rev)::numeric, 2) AS cum_share_pct,
               CASE WHEN 100.0 * cum_rev / total_rev <= 80 THEN 'A'
                    WHEN 100.0 * cum_rev / total_rev <= 95 THEN 'B'
                    ELSE 'C' END AS abc
        FROM cum ORDER BY revenue DESC LIMIT %s
    """, (lim,))
    if cls in ("A", "B", "C"):
        rows = [r for r in rows if r["abc"] == cls]
    return rows




SNAP = "order_status IN ('Машина отгружена', 'Отгружен')"


@app.get("/api/heatmap")
def heatmap(metric: str = "orders"):
    """Месяц×год-матрица: orders | revenue | avg. Строки=год (новый сверху), колонки=1..12."""
    metric = metric if metric in ("orders", "revenue", "avg") else "orders"
    agg = {"orders": "COUNT(*)::float8",
           "revenue": f"SUM(CASE WHEN {SNAP} THEN COALESCE(sum,0) ELSE 0 END)::float8",
           "avg": f"COALESCE(AVG(CASE WHEN order_status IN ('Машина отгружена', 'Отгружен') THEN COALESCE(sum,0) END),0)::float8"}[metric]
    rows = q(f"""
        SELECT EXTRACT(year FROM order_date)::int AS y,
               EXTRACT(month FROM order_date)::int AS m,
               {agg} AS v
        FROM orders WHERE order_date IS NOT NULL
        GROUP BY 1,2 ORDER BY 1,2
    """)
    years = sorted({r["y"] for r in rows}, reverse=True)
    matrix = {y: [0.0] * 12 for y in years}
    for r in rows:
        matrix[r["y"]][r["m"] - 1] = float(r["v"])
    return {"years": years, "matrix": matrix, "metric": metric}




@app.get("/api/search_all")
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




@app.get("/api/item/{nom_id}/card")
def item_card(nom_id: str):
    """Карточка товара: продажи (всего/12мес/последний раз), динамика цены (месяц-срезы), остатки по складам, покупают вместе."""
    sold_all = q1("""
        SELECT COALESCE(SUM(i.quantity),0)::float8 AS units, COALESCE(SUM(i.total),0)::float8 AS revenue,
               COUNT(DISTINCT i.orders_id)::int AS orders_cnt, MAX(o.order_date) AS last_order
        FROM order_items i JOIN orders o ON o.id = i.orders_id
        WHERE i.id_1c = %s AND i.kind = 'nomenclature'
    """, (nom_id,))
    sold12 = q1("""
        SELECT COALESCE(SUM(i.quantity),0)::float8 AS units, COALESCE(SUM(i.total),0)::float8 AS revenue
        FROM order_items i JOIN orders o ON o.id = i.orders_id
        WHERE i.id_1c = %s AND i.kind = 'nomenclature' AND o.order_date >= now() - interval '12 months'
    """, (nom_id,))
    # динамика цены: 1-й день месяца → min(discount_price) по 22789-агр-ветке (id 4d30…)
    price_hist = q("""
        SELECT to_char(version_date, 'YYYY-MM-01') AS month, MIN(discount_price)::float8 AS min_price,
               MAX(price)::float8 AS max_list
        FROM prices_history WHERE nomenclature_id = %s
        GROUP BY 1 ORDER BY 1
    """, (nom_id,))
    remnants = q("""
        SELECT COALESCE(b.name, r.storage_id) AS branch, r.qty, r.delivery_date, r.snapshot_date
        FROM remnants_snapshots r LEFT JOIN branches b ON b.id_1c = r.storage_id
        WHERE r.nomenclature_id = %s AND r.kind = 'metall' AND (r.qty > 0 OR r.delivery_date IS NOT NULL)
          AND r.snapshot_date = (SELECT MAX(s2.snapshot_date) FROM remnants_snapshots s2 WHERE s2.kind = 'metall')
        ORDER BY r.qty DESC
    """, (nom_id,))
    # покупают вместе: другие позиции, встречающиеся в тех же заказах
    together = q("""
        SELECT i2.name, COUNT(DISTINCT i2.orders_id)::int AS cnt, SUM(i2.quantity)::float8 AS units
        FROM order_items i2
        WHERE i2.orders_id IN (SELECT orders_id FROM order_items WHERE id_1c = %s)
          AND i2.id_1c <> %s AND i2.kind = 'nomenclature'
        GROUP BY 1 ORDER BY 2 DESC LIMIT 8
    """, (nom_id, nom_id))
    info = q1("SELECT id_1c, full_name, color, thickness, surface, weight, group_name, kind FROM nomenclature_full WHERE id_1c = %s", (nom_id,))
    if not info:
        info = q1("SELECT id_1c, name AS full_name, group_name FROM nomenclature WHERE id_1c = %s", (nom_id,))
    return {"info": info, "sold_all": sold_all, "sold12": sold12,
            "price_history": price_hist, "remnants": remnants, "together": together}




import time as _time
_REM_HIST_TTL = 60.0
_rem_hist_cache: dict = {}

@app.get("/api/remnants/history")
def remnants_history(nom_id: str = ""):
    _key = nom_id or "*"
    _hit = _rem_hist_cache.get(_key)
    if _hit and (_time.monotonic() - _hit[0]) < _REM_HIST_TTL:
        return _hit[1]
    _res = _remnants_history_impl(nom_id)
    _rem_hist_cache[_key] = (_time.monotonic(), _res)
    return _res

def _remnants_history_impl(nom_id: str = ""):
    """Динамика остатков по датам снапшотов. Быстро: 2-этапная-агрегация (GroupAggregate-без-сортировки-155МБ)."""
    dates = [r["d"].isoformat() for r in q("SELECT DISTINCT snapshot_date::date AS d FROM remnants_snapshots ORDER BY 1")]
    if nom_id:
        rows = q("""
            SELECT snapshot_date::date AS d, kind, SUM(qty)::float8 AS total_qty
            FROM remnants_snapshots WHERE nomenclature_id = %s GROUP BY 1,2 ORDER BY 1
        """, (nom_id,))
        series = {}
        for r_ in rows:
            series.setdefault(r_["kind"], []).append({"date": r_["d"].isoformat(), "qty": float(r_["total_qty"])})
        return {"dates": dates, "series": series}
    # индекс-по-(kind,snapshot_date)+INCLUDE-даёт-IndexOnly-агрегат; по-товару-считаем-отдельно-матвиew:
    rows = q("""
        SELECT r.snapshot_date::date AS d, r.kind, SUM(r.qty)::float8 AS total_qty,
               (SELECT COUNT(DISTINCT nomenclature_id) FROM remnants_snapshots r2
                 WHERE r2.kind = r.kind AND r2.snapshot_date = r.snapshot_date) AS items
        FROM remnants_snapshots r
        GROUP BY 1, 2 ORDER BY 1
    """)
    series = {}
    for r_ in rows:
        series.setdefault(r_["kind"], []).append({"date": r_["d"].isoformat(), "qty": float(r_["total_qty"]), "items": r_["items"]})
    return {"dates": dates, "series": series}

@app.get("/api/export/orders.csv")
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
    buf = _io.StringIO()
    w = _csv.writer(buf, delimiter=";")
    w.writerow(["id", "номер", "дата", "статус", "отгрузка", "контрагент", "сумма_заказа"])
    for r in rows:
        w.writerow([r["order_id"], r["number"], r["order_date"], r["order_status"], r["shipment_date"], r["contractor_name"], r["sum"]])
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv; charset=cp1251",
        headers={"Content-Disposition": "attachment; filename=orders.csv"})



import os as _os
from fastapi import Depends, HTTPException, status as _st
from fastapi.security import HTTPBasic, HTTPBasicCredentials as _Cred

_basic = HTTPBasic(auto_error=False)

def need_auth(cred: _Cred = Depends(_basic)):
    pwd = _os.getenv("WEB_PASSWORD", "")
    if not pwd:
        return  # без пароля
    if cred and cred.username == "m" and cred.password == pwd:
        return
    raise HTTPException(status_code=401, detail="auth", headers={"WWW-Authenticate": "Basic"})

# навесить need_auth на все JSON/HTML-роуты: проще-всего — middleware
@app.middleware("http")
async def basic_auth_mw(request, call_next):
    pwd = _os.getenv("WEB_PASSWORD", "")
    if pwd and not request.url.path.startswith(("/static",)):
        import base64
        hdr = request.headers.get("authorization", "")
        ok = False
        if hdr.startswith("Basic "):
            try:
                u, p = base64.b64decode(hdr[6:]).decode().split(":", 1)
                ok = (u == "m" and p == pwd)
            except Exception:
                ok = False
        if not ok:
            return PlainTextResponse("auth", status_code=401, headers={"WWW-Authenticate": "Basic realm=cinkoff"})
    return await call_next(request)




@app.get("/api/forecast/remnants")
def forecast_remnants(days: int = 90, top: int = 40):
    """Прогноз: для товаров с расходом — темп (шт/день) за период, остаток, хватит-на-дней. Только тот, что ЕСТЬ в остатках."""
    burnt = q("""
        SELECT i.id_1c, COALESCE(n.full_name, n2.name) AS name,
               SUM(i.quantity)::float8 AS spent, COUNT(DISTINCT i.orders_id)::int AS orders_cnt
        FROM order_items i
        JOIN orders o ON o.id = i.orders_id
        LEFT JOIN nomenclature_full n ON n.id_1c = i.id_1c
        LEFT JOIN nomenclature n2 ON n2.id_1c = i.id_1c
        WHERE i.kind = 'nomenclature' AND o.order_date >= now() - (%s || ' days')::interval
        GROUP BY 1, 2
    """, (str(days),))
    rem = q("""
        SELECT nomenclature_id, SUM(qty)::float8 AS stock
        FROM remnants_snapshots
        WHERE kind = 'metall' AND qty > 0
          AND snapshot_date = (SELECT MAX(snapshot_date) FROM remnants_snapshots WHERE kind = 'metall')
        GROUP BY 1
    """)
    stock = {r["nomenclature_id"]: r["stock"] for r in rem}
    out = []
    for r in burnt:
        nid = r["id_1c"]
        if nid not in stock:
            continue
        rate = r["spent"] / days  # шт/день
        out.append({
            "id_1c": nid, "name": r["name"],
            "spent": float(r["spent"]), "rate_day": round(rate, 2),
            "stock": float(stock[nid]),
            "days_left": round(stock[nid] / rate) if rate > 0 else None,
            "orders_cnt": r["orders_cnt"],
        })
    out.sort(key=lambda x: -(x["spent"] or 0))
    out = out[:max(5, min(200, top))]
    # категоризация
    for r in out:
        d = r["days_left"]
        r["flag"] = "crit" if (d is not None and d < 14) else ("warn" if (d is not None and d < 45) else "ok")
    return {"days": days, "rows": out}




@app.get("/api/basket/pairs")
def basket_pairs(days: int = 90, top: int = 15):
    """Топ-пар товаров, купленных в одном заказе (90д)."""
    rows = q("""
        SELECT a.nm AS a_name, b.nm AS b_name, COUNT(DISTINCT a.oid)::int AS cnt
        FROM (
            SELECT i.orders_id AS oid, i.id_1c AS aid, COALESCE(n1.full_name, n2.name) AS nm
            FROM order_items i
            LEFT JOIN nomenclature_full n1 ON n1.id_1c = i.id_1c
            LEFT JOIN nomenclature n2 ON n2.id_1c = i.id_1c
            WHERE i.kind = 'nomenclature' AND i.id_1c IS NOT NULL
        ) a
        JOIN (
            SELECT i.orders_id AS oid, i.id_1c AS aid, COALESCE(n1.full_name, n2.name) AS nm
            FROM order_items i
            LEFT JOIN nomenclature_full n1 ON n1.id_1c = i.id_1c
            LEFT JOIN nomenclature n2 ON n2.id_1c = i.id_1c
            WHERE i.kind = 'nomenclature' AND i.id_1c IS NOT NULL
        ) b ON a.oid = b.oid AND a.aid < b.aid
        JOIN orders o ON o.id = a.oid
        WHERE o.order_date >= now() - (%s || ' days')::interval
        GROUP BY 1, 2 ORDER BY 3 DESC LIMIT %s
    """, (str(days), max(3, min(50, top))))
    return {"pairs": rows}



@app.get("/api/cohorts")
def cohorts():
    """Активность точек-продаж (филиалов): новых-по-месяцам, всего-активных, повтор-в-90д, топ-точек-по-выручке."""
    new_m = q("""
        SELECT to_char(first_m, 'YYYY-MM') AS month, COUNT(*)::int AS newcnt
        FROM (SELECT branch_id_1c, MIN(date_trunc('month', order_date)) AS first_m
              FROM orders WHERE branch_id_1c IS NOT NULL AND order_date IS NOT NULL
              GROUP BY 1) t
        GROUP BY 1 ORDER BY 1
    """)
    act_m = q("""
        SELECT to_char(date_trunc('month', order_date), 'YYYY-MM') AS month,
               COUNT(DISTINCT branch_id_1c)::int AS active_branches,
               COUNT(*)::int AS orders_cnt
        FROM orders WHERE branch_id_1c IS NOT NULL AND order_date IS NOT NULL
        GROUP BY 1 ORDER BY 1
    """)
    ret = q("""
        WITH pm AS (
            SELECT branch_id_1c, date_trunc('month', order_date) AS m
            FROM orders WHERE branch_id_1c IS NOT NULL AND order_date IS NOT NULL
            GROUP BY 1, 2
        ),
        fm AS (
            SELECT DISTINCT a.branch_id_1c, a.m
            FROM pm a
            WHERE EXISTS (SELECT 1 FROM pm b WHERE b.branch_id_1c = a.branch_id_1c
                          AND b.m > a.m AND b.m <= a.m + interval '3 months')
        )
        SELECT to_char(pm.m, 'YYYY-MM') AS month,
               COUNT(*)::int AS branches_this_m,
               COUNT(fm.branch_id_1c)::int AS returned_next3
        FROM pm LEFT JOIN fm ON fm.branch_id_1c = pm.branch_id_1c AND fm.m = pm.m
        GROUP BY 1 ORDER BY 1
    """)
    top = q("""
        SELECT COALESCE(b.name, '—') AS branch, COUNT(*)::int AS orders_cnt,
               SUM(CASE WHEN order_status IN ('Машина отгружена', 'Отгружен') THEN COALESCE(sum,0) ELSE 0 END)::float8 AS revenue
        FROM orders o LEFT JOIN branches b ON b.id_1c = o.branch_id_1c
        WHERE o.order_date >= now() - interval '12 months'
        GROUP BY 1 ORDER BY 3 DESC
    """)
    return {"new_by_month": new_m, "active_by_month": act_m, "retention": ret, "top_branches": top}

@app.get("/api/branches")
def branches():
    return q("SELECT id_1c, name, address, latitude, longitude FROM branches ORDER BY name")


@app.get("/healthz")
def healthz():
    try:
        with _cur() as cur:
            cur.execute("SELECT 1")
        return {"ok": True, "pool": {"used": len(_pool._used) if _pool else 0, "conns": len(_pool._pool) if _pool else 0}}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)[:200]}, status_code=503)


# ── Статика SPA ──
app.mount("/static", StaticFiles(directory=os.path.join(BASE, "static")), name="static")


@app.get("/", response_class=HTMLResponse)
def spa():
    # R4: главная теперь = v2; легаси-SPA живёт на /legacy (и по-старому на /static/index.html)
    p = os.path.join(BASE, "static_v2", "index.html")
    with open(p, "rb") as f:
        return HTMLResponse(f.read().decode("utf-8"))


@app.get("/legacy", response_class=HTMLResponse, include_in_schema=False)
def legacy_spa():
    p = os.path.join(BASE, "static", "index.html")
    with open(p, "rb") as f:
        return HTMLResponse(f.read().decode("utf-8"))


# ── SPA v2 (Vue3+Vite+TS, каталог static_v2; легаси не тронут) ──
_V2 = os.path.join(BASE, "static_v2")
if os.path.isdir(_V2):

    class SPAStaticFiles(StaticFiles):
        """StaticFiles + SPA-fallback: несуществующий путь (без расширения) → index.html."""

        async def get_response(self, path: str, scope):
            try:
                resp = await super().get_response(path, scope)
            except StarletteHTTPException as e:
                if e.status_code == 404:
                    return FileResponse(os.path.join(self.directory, "index.html"))
                raise
            if resp.status_code == 404:
                return FileResponse(os.path.join(self.directory, "index.html"))
            return resp

    app.mount("/v2", SPAStaticFiles(directory=_V2, html=True), name="v2")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
