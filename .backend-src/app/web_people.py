"""Люди-зона веб-слоя: 3 роута (summary, monthly, compare) + хелперы окон/грануляра.

Фаза 4 рефакторинга (docs/REFACTOR_PLAN.md): чистое перемещение из web.py, логика без изменений
(7 повторов WHERE-блока не дедуплицируются — это фаза 7). Регистрируется в web.py через
include_router — пути/параметры дословно как были.
"""
from __future__ import annotations

import datetime

from fastapi import APIRouter

from web_common import q

_PEOPLE_WHERE_ALL  = "shipment_date IS NOT NULL AND demand_responsible IS NOT NULL AND demand_responsible <> ''"
_PEOPLE_WHERE_ONE  = "shipment_date IS NOT NULL AND demand_responsible = %s"
_PEOPLE_WHERE_MANY = "shipment_date IS NOT NULL AND demand_responsible = ANY(%s)"

router = APIRouter()


def _gran_for(months: int, ship_from: str, ship_to: str) -> str:
    """Грануляр-графика-по-ДЛИНЕ-выбранного-периода: <=31-день → по-дням, <=200-дней → по-неделям, иначе-месяцы.
    Без-дат-—-по-кол-ву-месяцев (месяц→день, до-полугода→неделя, дальше-месяц)."""
    if ship_from and ship_to:
        try:
            _d = __import__("datetime").date
            span = (_d.fromisoformat(ship_to) - _d.fromisoformat(ship_from)).days + 1
            if 0 < span <= 31:
                return "day"
            if 0 < span <= 200:
                return "week"
            return "month"
        except Exception:
            pass
    return "day" if months <= 1 else ("week" if months <= 6 else "month")


def _window_clause(ship_from: str, months: int) -> str:
    """SQL-окно-начала-периода: с-заданным-ship_from —- жёстко-от-него; без-—-скользящие-месяцы-от-сегодня."""
    if ship_from:
        return f"AND shipment_date >= '{ship_from}'::date"
    return f"AND shipment_date >= (CURRENT_DATE - ({months} || ' months')::interval)"

def _days_clause(ship_from: str, ship_to: str) -> "tuple[str, tuple]":
    """Условие-по-датам-отгрузки (для-чипов-Сегодня/Вчера/Неделя). Пустые-не-фильтруют."""
    if not ship_from and not ship_to:
        return "", []
    parts, args = [], []
    if ship_from:
        parts.append("shipment_date::date >= %s"); args.append(ship_from)
    if ship_to:
        parts.append("shipment_date::date <= %s"); args.append(ship_to)
    return " AND " + " AND ".join(parts), args


@router.get("/api/people/summary")
def people_summary(months: int = 12, ship_from: str = "", ship_to: str = ""):
    """Сводка-по-ответственным: продажи-= отгруженные-заказы (shipment_date-задан).
    Таблица-за-послед-N-месяцев + динамика-к-прошлому-году-в-тот-же-месяц."""
    months = max(1, min(120, months))
    dsql, dargs = _days_clause(ship_from, ship_to)
    win = _window_clause(ship_from, months)
    rows = q(f"""
        WITH shipped AS (
            SELECT demand_responsible AS person,
                   date_trunc('month', shipment_date) AS m,
                   COUNT(*)::int AS deals,
                   COALESCE(SUM(sum), 0)::float8 AS revenue
            FROM orders
            WHERE {_PEOPLE_WHERE_ALL}
              AND TO_CHAR(shipment_date, 'YYYY-MM') <= TO_CHAR(CURRENT_DATE, 'YYYY-MM')
              {win}
              {dsql}
            GROUP BY 1, 2
        )
        SELECT person,
               SUM(deals)::int                        AS deals_total,
               ROUND(SUM(revenue)::numeric / 1e6, 2)::float8 AS revenue_mln,
               ROUND(AVG(deals)::numeric, 1)::float8  AS deals_per_month,
               ROUND((SUM(revenue) / COUNT(DISTINCT m))::numeric / 1e6, 2)::float8 AS avg_month_revenue_mln,
               MIN(m)::text                           AS first_month
        FROM shipped GROUP BY 1
        ORDER BY SUM(revenue) DESC
    """, tuple(dargs))
    # MoM-динамика-последнего-месяца-и-среднее-по-персоне-для-тренда:
    trend = q(f"""
        SELECT demand_responsible AS person,
               TO_CHAR(date_trunc('month', shipment_date), 'YYYY-MM') AS month,
               COUNT(*)::int AS deals,
               COALESCE(SUM(sum), 0)::float8 AS revenue
        FROM orders
        WHERE {_PEOPLE_WHERE_ALL}
          AND TO_CHAR(shipment_date, 'YYYY-MM') <= TO_CHAR(CURRENT_DATE, 'YYYY-MM')
          {win}
          {dsql}
        GROUP BY 1, 2 ORDER BY 2, 1
    """, tuple(dargs))
    by_person: dict = {}
    for r in trend:
        by_person.setdefault(r["person"], []).append({"month": r["month"], "deals": r["deals"], "revenue": r["revenue"]})
    # ── динамика-ПО-ДНЯМ (для-чипов-Сегодня/Вчера/Неделя —- иначе-график-одна-точка) ──
    by_day: dict = {}
    if ship_from or ship_to:
        drows = q(f"""
            SELECT demand_responsible AS person,
                   TO_CHAR(shipment_date, 'YYYY-MM-DD') AS day,
                   COUNT(*)::int AS deals,
                   COALESCE(SUM(sum), 0)::float8 AS revenue
            FROM orders
            WHERE {_PEOPLE_WHERE_ALL}
              AND TO_CHAR(shipment_date, 'YYYY-MM') <= TO_CHAR(CURRENT_DATE, 'YYYY-MM')
              {dsql}
            GROUP BY 1, 2 ORDER BY 2, 1
        """, tuple(dargs))
        for r in drows:
            by_day.setdefault(r["person"], []).append({"day": r["day"], "deals": r["deals"], "revenue": r["revenue"]})
    return {"period_months": months, "summary": rows, "by_month": by_person, "by_day": by_day}


@router.get("/api/people/monthly")
def people_monthly(person: str, months: int = 24, ship_from: str = "", ship_to: str = ""):
    """Помесячные-продажи-одного-человека: заказы, выручка, средний-чек.
    Плюс-тот-же-месяц-прошлого-года (для-«год-к-году»).
    gran: месяц≤1 → ПО-ДНЯМ, ≤6 → ПО-НЕДЕЛЯМ (промежуточные-точки-графика), дальше → месяцы.
    monthly-всегда-помесячно (для-таблицы), series —- в-грануляре gran (для-графика)."""
    months = max(1, min(120, months))
    dsql, dargs = _days_clause(ship_from, ship_to)
    win = _window_clause(ship_from, months)
    cur = q(f"""
        SELECT TO_CHAR(date_trunc('month', shipment_date), 'YYYY-MM') AS month,
               COUNT(*)::int AS deals,
               COALESCE(SUM(sum), 0)::float8 AS revenue,
               COALESCE(AVG(sum), 0)::float8 AS avg_check
        FROM orders
        WHERE {_PEOPLE_WHERE_ONE}
          AND TO_CHAR(shipment_date, 'YYYY-MM') <= TO_CHAR(CURRENT_DATE, 'YYYY-MM')
          {win}
          {dsql}
        GROUP BY 1 ORDER BY 1
    """, tuple([person] + list(dargs)))
    _to_eff = ship_to or (datetime.date.today().isoformat())
    # прошлый-год-в-то-же-месяц: ровно-то-же-ОКНО, сд-В-И-Н-У-ТОЕ-на-1-год-назад.
    # КЛЮЧ pm = натуральный-месяц +1-год → фронт-берёт-по-ТО-МУ-же-месяцу-оси (pyMap[m.month]).
    if ship_from:
        _to = _to_eff
        _win_sql = (f"AND shipment_date >= '{ship_from}'::date - interval '1 year' "
                    f"AND shipment_date < '{_to}'::date + interval '1 day' - interval '1 year'")
    else:
        _win_sql = (f"AND shipment_date >= (CURRENT_DATE - ({months} || ' months')::interval) - interval '1 year' "
                    f"AND shipment_date < (CURRENT_DATE - interval '1 year') + interval '1 day'")
    prev_year = q(f"""
        SELECT TO_CHAR(date_trunc('month', shipment_date) + interval '1 year', 'YYYY-MM') AS pm,
               COUNT(*)::int AS deals, COALESCE(SUM(sum), 0)::float8 AS revenue,
               COALESCE(AVG(sum), 0)::float8 AS avg_check
        FROM orders
        WHERE {_PEOPLE_WHERE_ONE}
          {_win_sql}
        GROUP BY 1 ORDER BY 1
    """, (person,))
    # гранулярная-разбивка-для-ГРАФИКА: по-длине-диапазона (или-по-кол-ву-месяцев)
    gran = _gran_for(months, ship_from, ship_to)
    if gran == "day":
        bucket = "TO_CHAR(shipment_date, 'YYYY-MM-DD')"
    elif gran == "week":
        bucket = "TO_CHAR(date_trunc('week', shipment_date), 'YYYY-MM-DD')"  # ISO-неделя, старт-пн
    else:
        bucket = "TO_CHAR(date_trunc('month', shipment_date), 'YYYY-MM')"
    extra_date = "AND shipment_date <= CURRENT_DATE" if gran != "month" else ""  # план-за-горизонтом-не-рисуем
    series = q(f"""
        SELECT {bucket} AS period,
               COUNT(*)::int AS deals,
               COALESCE(SUM(sum), 0)::float8 AS revenue
        FROM orders
        WHERE {_PEOPLE_WHERE_ONE}
          AND TO_CHAR(shipment_date, 'YYYY-MM') <= TO_CHAR(CURRENT_DATE, 'YYYY-MM')
          {win}
          {extra_date}
          {dsql}
        GROUP BY 1 ORDER BY 1
    """, tuple([person] + list(dargs)))
    return {"person": person, "months": months, "gran": gran, "series": series,
            "monthly": cur, "prev_year_same_month": (prev_year if gran == "month" else [])}


@router.get("/api/people/compare")
def people_compare(people: str, months: int = 12, ship_from: str = "", ship_to: str = ""):
    """Сравнение-нескольких-людей (до-5). people=Иван;Мария;...
    грануляр-графика: месяц≤1 → ПО-ДНЯМ, ≤6 → ПО-НЕДЕЛЯМ, дальше → месяцы (поля-«month»-несут-период)."""
    months = max(1, min(120, months))
    dsql, dargs = _days_clause(ship_from, ship_to)
    win = _window_clause(ship_from, months)
    persons = [p.strip() for p in (people or "").split(";") if p.strip()][:5]
    if not persons:
        return {"gran": "month", "months": [], "series": {}}
    gran = _gran_for(months, ship_from, ship_to)
    if gran == "day":
        bucket = "TO_CHAR(shipment_date, 'YYYY-MM-DD')"
    elif gran == "week":
        bucket = "TO_CHAR(date_trunc('week', shipment_date), 'YYYY-MM-DD')"
    else:
        bucket = "TO_CHAR(date_trunc('month', shipment_date), 'YYYY-MM')"
    extra_date = "AND shipment_date <= CURRENT_DATE" if gran != "month" else ""  # план-за-горизонтом-не-рисуем
    rows = q(f"""
        SELECT demand_responsible AS person,
               {bucket} AS month,
               COUNT(*)::int AS deals,
               COALESCE(SUM(sum), 0)::float8 AS revenue
        FROM orders
        WHERE {_PEOPLE_WHERE_MANY}
          AND TO_CHAR(shipment_date, 'YYYY-MM') <= TO_CHAR(CURRENT_DATE, 'YYYY-MM')  -- только-прошедшие-месяцы (сезон-уже-в-буд-есть-плановые-отгрузки)
          {win}
          {extra_date}
          {dsql}
        GROUP BY 1, 2 ORDER BY 2, 1
    """, tuple([persons] + list(dargs)))
    series: dict = {}
    months_axis = sorted({r["month"] for r in rows})
    _today = __import__("datetime").date.today().strftime("%Y-%m" if gran == "month" else "%Y-%m-%d")
    if gran == "month":
        months_axis = [mth for mth in months_axis if mth <= _today]
    for p_ in persons:
        m = {r["month"]: r for r in rows if r["person"] == p_}
        series[p_] = [{"month": mth, "deals": m.get(mth, {}).get("deals", 0),
                       "revenue": m.get(mth, {}).get("revenue", 0)} for mth in months_axis]
    # месячная-ось-ДЛЯ-ТАБЛИЦЫ-дельт (посл-месяц/MoM/YoY-—-всегда-помесячно, независимо-от-грануляра-графика):
    mrows = q(f"""
        SELECT demand_responsible AS person,
               TO_CHAR(date_trunc('month', shipment_date), 'YYYY-MM') AS month,
               COUNT(*)::int AS deals,
               COALESCE(SUM(sum), 0)::float8 AS revenue
        FROM orders
        WHERE {_PEOPLE_WHERE_MANY}
          AND TO_CHAR(shipment_date, 'YYYY-MM') <= TO_CHAR(CURRENT_DATE, 'YYYY-MM')
          {win}
          {dsql}
        GROUP BY 1, 2 ORDER BY 2, 1
    """, tuple([persons] + list(dargs)))
    ms_axis = sorted({r["month"] for r in mrows})
    ms_axis = [mth for mth in ms_axis if mth <= __import__("datetime").date.today().strftime("%Y-%m")]
    series_m: dict = {}
    for p_ in persons:
        m = {r["month"]: r for r in mrows if r["person"] == p_}
        series_m[p_] = [{"month": mth, "deals": m.get(mth, {}).get("deals", 0),
                         "revenue": m.get(mth, {}).get("revenue", 0)} for mth in ms_axis]
    return {"gran": gran, "months": months_axis, "series": series,
            "months_monthly": ms_axis, "series_monthly": series_m}
