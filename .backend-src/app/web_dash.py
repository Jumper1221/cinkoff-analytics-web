"""Дашборд-зона веб-слоя: 15 сводных роутов (kpi, years, monthly, top/contractors, top/items,
status_breakdown, freshness, compare, leadtime, cancel_rate, stale, abc, heatmap, cohorts, branches).

Фаза 6 рефакторинга (docs/REFACTOR_PLAN.md): чистое перемещение из web.py, логика/SQL без изменений.
Регистрируется в web.py через include_router — пути/параметры дословно как были.
"""
from __future__ import annotations

import datetime

from fastapi import APIRouter

from web_common import q, q1, SNAP

router = APIRouter()


@router.get("/api/kpi")
def kpi():
    return q1(f"""
        SELECT
          (SELECT COUNT(*)::int FROM orders WHERE order_date::date = (now() AT TIME ZONE 'Europe/Moscow')::date) AS orders_today,
          (SELECT COUNT(*)::int FROM orders WHERE order_date >= now() - interval '30 days') AS orders_30d,
          (SELECT COALESCE(SUM(CASE WHEN {SNAP} THEN COALESCE(sum,0) ELSE 0 END),0)::float8 FROM orders WHERE order_date >= now() - interval '30 days') AS sum_30d,
          (SELECT COUNT(*)::int FROM orders WHERE order_date >= now() - interval '30 days' AND order_status = 'Машина отгружена') AS shipped_30,
          (SELECT AVG(CASE WHEN {SNAP} THEN COALESCE(sum,0) END)::float8 FROM orders WHERE order_date >= now() - interval '30 days') AS avg_30
    """)


@router.get("/api/years")
def years():
    return q(f"""
        SELECT EXTRACT(year FROM order_date)::int AS year,
               COUNT(*)::int AS cnt,
               SUM(CASE WHEN {SNAP} THEN COALESCE(sum,0) ELSE 0 END)::float8 AS revenue,
               AVG(CASE WHEN {SNAP} THEN COALESCE(sum,0) END)::float8 AS avg_check,
               COUNT(*) FILTER (WHERE {SNAP})::int AS done_cnt
        FROM orders WHERE order_date IS NOT NULL
        GROUP BY 1 ORDER BY 1
    """)


@router.get("/api/monthly")
def monthly(months: int = 24):
    months = max(1, min(120, months))
    return q(f"""
        SELECT EXTRACT(year FROM order_date)::int AS year,
               EXTRACT(month FROM order_date)::int AS month,
               COUNT(*)::int AS cnt,
               SUM(CASE WHEN {SNAP} THEN COALESCE(sum,0) ELSE 0 END)::float8 AS total,
               COUNT(*) FILTER (WHERE {SNAP})::int AS done_cnt
        FROM orders WHERE order_date >= now() - interval '{months} months'
        GROUP BY 1,2 ORDER BY 1,2
    """)


@router.get("/api/top/contractors")
def top_contractors(limit: int = 10, days: int = 365):
    limit = max(1, min(50, limit))
    days = max(30, min(3650, days))
    return q(f"""
        SELECT contractor_name AS name, COUNT(*)::int AS orders,
               SUM(CASE WHEN {SNAP} THEN COALESCE(sum,0) ELSE 0 END)::float8 AS revenue
        FROM orders
        WHERE contractor_name IS NOT NULL AND order_date >= now() - interval '{days} days'
        GROUP BY 1 ORDER BY 2 DESC LIMIT {limit}
    """)


@router.get("/api/top/items")
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


@router.get("/api/status_breakdown")
def status_breakdown(days: int = 365):
    days = max(30, min(3650, days))
    return q(f"""
        SELECT COALESCE(order_status, '—') AS status, COUNT(*)::int AS cnt
        FROM orders WHERE order_date >= now() - interval '{days} days'
        GROUP BY 1 ORDER BY 2 DESC
    """)


@router.get("/api/freshness")
def freshness():
    r = q1("SELECT MAX(order_date)::date AS last_order, COUNT(*)::int AS total, COUNT(*)::int AS total_orders FROM orders")
    # примечание:fresh.last_order/total, total_orders дублирует total для шаблона
    return r


@router.get("/api/compare")
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


@router.get("/api/leadtime")
def leadtime(months: int = 12):
    """Скорость исполнения: медиана дней заказ→shipment_date по месяцам + % отмен."""
    months = max(1, min(120, months))
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


@router.get("/api/cancel_rate")
def cancel_rate(months: int = 12):
    """% отмен по месяцам (по дате заказа)."""
    months = max(1, min(120, months))
    return q(f"""
        SELECT to_char(date_trunc('month', order_date), 'YYYY-MM') AS label,
               COUNT(*)::int AS orders,
               COUNT(*) FILTER (WHERE order_status = 'Отменен')::int AS canceled,
               ROUND(100.0 * COUNT(*) FILTER (WHERE order_status = 'Отменен') / COUNT(*), 1) AS pct
        FROM orders
        WHERE order_date >= now() - interval '{months} months'
        GROUP BY 1 ORDER BY 1
    """)


@router.get("/api/stale")
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


@router.get("/api/abc")
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


@router.get("/api/heatmap")
def heatmap(metric: str = "orders"):
    """Месяц×год-матрица: orders | revenue | avg. Строки=год (новый сверху), колонки=1..12."""
    metric = metric if metric in ("orders", "revenue", "avg") else "orders"
    agg = {"orders": "COUNT(*)::float8",
           "revenue": f"SUM(CASE WHEN {SNAP} THEN COALESCE(sum,0) ELSE 0 END)::float8",
           "avg": f"COALESCE(AVG(CASE WHEN {SNAP} THEN COALESCE(sum,0) END),0)::float8"}[metric]
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


@router.get("/api/cohorts")
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
    top = q(f"""
        SELECT COALESCE(b.name, '—') AS branch, COUNT(*)::int AS orders_cnt,
               SUM(CASE WHEN {SNAP} THEN COALESCE(sum,0) ELSE 0 END)::float8 AS revenue
        FROM orders o LEFT JOIN branches b ON b.id_1c = o.branch_id_1c
        WHERE o.order_date >= now() - interval '12 months'
        GROUP BY 1 ORDER BY 3 DESC
    """)
    return {"new_by_month": new_m, "active_by_month": act_m, "retention": ret, "top_branches": top}

@router.get("/api/branches")
def branches():
    return q("SELECT id_1c, name, address, latitude, longitude FROM branches ORDER BY name")
