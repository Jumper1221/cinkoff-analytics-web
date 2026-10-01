"""Склад-зона веб-слоя: remnants×3 (остатки/даты/история) + forecast/remnants + basket/pairs.

Фаза 5 рефакторинга (docs/REFACTOR_PLAN.md): чистое перемещение из web.py, логика без изменений
(TTL-кэш remnants/history переезжает как есть, без оптимизации). Регистрируется в web.py через
include_router — пути/параметры дословно как были.
"""
from __future__ import annotations

from fastapi import APIRouter

from web_common import q, q1

router = APIRouter()


@router.get("/api/remnants")
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


@router.get("/api/remnants/dates")
def remnants_dates():
    r = q("SELECT DISTINCT snapshot_date::text AS d FROM remnants_snapshots ORDER BY 1 DESC LIMIT 30")
    return {"dates": [x["d"] for x in r]}


import time as _time
_REM_HIST_TTL = 60.0
_rem_hist_cache: dict = {}

@router.get("/api/remnants/history")
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


@router.get("/api/forecast/remnants")
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


_BASKET_ITEM = """
    SELECT i.orders_id AS oid, i.id_1c AS aid, COALESCE(n1.full_name, n2.name) AS nm
    FROM order_items i
    LEFT JOIN nomenclature_full n1 ON n1.id_1c = i.id_1c
    LEFT JOIN nomenclature n2 ON n2.id_1c = i.id_1c
    WHERE i.kind = 'nomenclature' AND i.id_1c IS NOT NULL
"""


@router.get("/api/basket/pairs")
def basket_pairs(days: int = 90, top: int = 15):
    """Топ-пар товаров, купленных в одном заказе (90д)."""
    rows = q(f"""
        SELECT a.nm AS a_name, b.nm AS b_name, COUNT(DISTINCT a.oid)::int AS cnt
        FROM ({_BASKET_ITEM}) a
        JOIN ({_BASKET_ITEM}) b ON a.oid = b.oid AND a.aid < b.aid
        JOIN orders o ON o.id = a.oid
        WHERE o.order_date >= now() - (%s || ' days')::interval
        GROUP BY 1, 2 ORDER BY 3 DESC LIMIT %s
    """, (str(days), max(3, min(50, top))))
    return {"pairs": rows}
