"""Контракт-тесты веб-слоя (Фаза 1, раздел 5 REFACTOR_PLAN.md, рубеж A) — без БД.

TestClient + monkeypatch q/q1 с фикстурными данными. Проверяет:
(а) golden-список всех 40 маршрутов (лишний/пропавший = красный);
(б) структуру ответов по таблице «путь → ожидаемая структура»;
(в) клэмпы: limit=9999→200, months=0→1 / months=999→120, steps=0→1 / 999→5, пустой branch;
(г) 404 у order_full с несуществующим id; 409 при втором POST /api/sync.

Запуск: python -m pytest app/ -q
"""
from __future__ import annotations

import copy
import contextlib
import datetime

import pytest
from fastapi.routing import APIRoute
from starlette.testclient import TestClient

import catalog_tree_build
import web  # импорт web добавляет app/ в sys.path
import web_catalog
import web_common
import web_dash
import web_orders
import web_people
import web_stock
import web_sync


# ── Фикстуры ответов (форма ровно как возвращает SQL-запрос роута) ──────────────────

KPI = {"orders_today": 1, "orders_30d": 120, "sum_30d": 987654.3, "shipped_30": 88, "avg_30": 11223.3}
YEAR = {"year": 2026, "cnt": 10, "revenue": 123.45, "avg_check": 12.3, "done_cnt": 9}
MONTH = {"year": 2026, "month": 9, "cnt": 4, "total": 55.5, "done_cnt": 3}
TOP_CONTR = {"name": "ООО Ромашка", "orders": 7, "revenue": 4242.0}
TOP_ITEM = {"name": "Металлочерепица Кредо 0.5", "units": 12, "revenue": 3000.0}
STATUS = {"status": "Машина отгружена", "cnt": 5}
FRESHNESS = {"last_order": "2026-09-30", "total": 11, "total_orders": 22}
ORDER = {"id": 1, "order_id": 900, "number": "УО-1", "order_date": "2026-09-01", "order_status": "Отгружен",
         "contractor_name": "ООО Ромашка", "branch_name": "4d300c12", "sum": 111.0}
EXPORT_ORDER = {"order_id": 900, "number": "УО-1", "order_date": "2026-09-01", "order_status": "Отгружен",
                "shipment_date": "2026-09-02", "contractor_name": "ООО Ромашка", "sum": 111.0}
ORDER_HEAD = {"id": 1, "order_id": 900, "number": "УО-1", "order_date": "2026-09-01"}
ORDER_ITEM = {"kind": "nomenclature", "id_1c": "N-1", "code_1c": "0001", "name": "Металлочерепица Кредо 0.5",
              "group_name": "Металлочерепица Кредо", "unit": "м2", "quantity": 10.0, "price": 700.0,
              "discount_pct": 5.0, "discount_price": 665.0, "total": 6650.0}
DEMAND_ITEM = {"kind": "nomenclature", "id_1c": "N-1", "name": "Металлочерепица Кредо 0.5", "quantity": 10.0,
               "price": 700.0, "discount_pct": 5.0, "discount_price": 665.0, "total": 6650.0}
SHIPMENT = {"shipment_number": "RT-1", "state": "Проведен", "driver_name": "Иван", "driver_phone": "+7-900-000-00-00",
            "source": "1c", "updated_at": "2026-09-02 10:00:00"}
SALE = {"number": "Р-1", "sales_date": "2026-09-03", "ware_sum": 100.0, "service_sum": 0.0, "total_sum": 100.0,
        "posted": True, "deletion_mark": False, "subcontractor": "", "kind": "nomenclature"}
STATUS_HIST = {"snapshot_date": "2026-09-01", "order_status": "Отгружен", "payment_status": "Оплачен",
               "sale_status": "Отгружен"}
COMPARE = {"orders": 5, "revenue": 12345.6, "avg_check": 2469.1, "canceled": 1}
LEAD = {"label": "2026-09", "median_days": 7.5, "p90_days": 14.2, "shipped": 9}
CANCEL = {"label": "2026-09", "orders": 5, "canceled": 1, "pct": 20.0}
STALE = {"order_id": 901, "number": "УО-9", "order_date": "2026-09-01", "order_status": "В работе",
         "contractor_name": "ООО Ромашка", "branch_name": "4d300c12", "sum": 111.0, "age_days": 12}
ABC = {"name": "Металлочерепица Кредо 0.5", "revenue": 5000.0, "units": 7.5, "share_pct": 12.34,
       "cum_share_pct": 45.67, "abc": "A"}
HEAT = {"y": 2026, "m": 9, "v": 5.0}
COHORT_NEW = {"month": "2026-01", "newcnt": 2}
COHORT_ACT = {"month": "2026-02", "active_branches": 3, "orders_cnt": 30}
COHORT_RET = {"month": "2026-01", "branches_this_m": 2, "returned_next3": 1}
COHORT_TOP = {"branch": "Склад-1", "orders_cnt": 40, "revenue": 90000.0}
BRANCH = {"id_1c": "4d300c12-11ed-11ec-8d1b-0025905ea25b", "name": "Склад-1", "address": "ул. Полевая, 1",
          "latitude": 54.7, "longitude": 20.5}
CAT_SEARCH = {"id_1c": "N-1", "full_name": "Металлочерепица Кредо 0.5 Polyester", "color": "RR23",
              "thickness": 0.5, "surface": "Полиэстер", "weight": 4.8, "group_name": "Металлочерепица Кредо",
              "branches": 2}
CAT_PRICE = {"branch_id_1c": "4d300c12", "branch": "Склад-1", "price": 700.0, "discount_pct": 5.0,
             "discount_price": 665.0, "version_date": "2026-09-01"}
PRICE_HIST = {"version_date": "2026-09-01", "branch_id_1c": "4d300c12", "branch": "Склад-1", "price": 700.0,
              "discount_price": 665.0}
TREE_KIND = {"kind": "Продукция", "n_items": 5}
TREE_GROUP = {"kind": "Продукция", "group_name": "Металлочерепица Кредо", "n_items": 3, "n_priced": 2}
# Фаза 3: снапшот catalog_tree_stats (те же счётчики, что TREE_KIND/TREE_GROUP, + family):
TREE_TS = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1)  # свежий built_at
TREE_STATS = [
    {"kind": "Продукция", "family": "Металлочерепица", "group_name": "Металлочерепица Кредо",
     "n_items": 3, "n_priced": 2, "kind_total": 3, "built_at": TREE_TS},
]
CAT_BRANCH = {"id_1c": "4d300c12-11ed-11ec-8d1b-0025905ea25b", "name": "Склад-1", "n_items": 9}
CAT_ITEM = {"id_1c": "N-1", "code_1c": "0001", "full_name": "Металлочерепица Кредо 0.5 Polyester",
            "group_name": "Металлочерепица Кредо", "color": "RR23", "thickness": 0.5, "surface": "Полиэстер",
            "price": 700.0, "discount_pct": 5.0, "discount_price": 665.0, "version_date": "2026-09-01"}
SURF = {"surf": "Полиэстер матовый", "n": 7}
REMNANT = {"nomenclature_id": "N-1", "full_name": "Металлочерепица Кредо 0.5", "storage_id": "4d300c12",
           "branch": "Склад-1", "qty": 10.0, "delivery_date": "2026-10-01", "snapshot_date": "2026-09-30"}
HIST_ALL = {"d": datetime.date(2026, 9, 8), "kind": "metall", "total_qty": 25.0, "items": 3}
HIST_NOM = {"d": datetime.date(2026, 9, 8), "kind": "metall", "total_qty": 4.0}
CARD_INFO = {"id_1c": "N-1", "full_name": "Металлочерепица Кредо 0.5 Polyester", "color": "RR23",
             "thickness": 0.5, "surface": "Полиэстер", "weight": 4.8, "group_name": "Металлочерепица Кредо",
             "kind": "Продукция"}
SOLD_ALL = {"units": 33.0, "revenue": 21000.0, "orders_cnt": 4, "last_order": "2026-09-01"}
SOLD12 = {"units": 12.0, "revenue": 8000.0}
CARD_PRICE = {"month": "2026-09-01", "min_price": 665.0, "max_list": 700.0}
CARD_REM = {"branch": "Склад-1", "qty": 10.0, "delivery_date": "2026-10-01", "snapshot_date": "2026-09-30"}
TOGETHER = {"name": "Планка направления", "cnt": 2, "units": 6.0}
SR_ORDER = {"order_id": 900, "number": "УО-1", "order_date": "2026-09-01", "order_status": "Отгружен",
            "contractor_name": "ООО Ромашка", "sum": 111.0}
SR_ITEM = {"id_1c": "N-1", "full_name": "Металлочерепица Кредо 0.5 Polyester", "color": "RR23", "thickness": 0.5}
BURNT = {"id_1c": "N-1", "name": "Металлочерепица Кредо 0.5 Polyester", "spent": 10.0, "orders_cnt": 2}
PAIR = {"a_name": "Металлочерепица Кредо 0.5", "b_name": "Планка направления", "cnt": 3}
P_SUMMARY = {"person": "Иван", "deals_total": 30, "revenue_mln": 3.2, "deals_per_month": 2.5,
             "avg_month_revenue_mln": 0.25, "first_month": "2025-10"}
P_TREND = {"person": "Иван", "month": "2026-08", "deals": 3, "revenue": 250000.0}
P_CUR = {"month": "2026-09", "deals": 5, "revenue": 400000.0, "avg_check": 50000.0}
P_PREV = {"pm": "2025-09", "deals": 2, "revenue": 90000.0, "avg_check": 25000.0}
P_SERIES = {"period": "2026-09", "deals": 3, "revenue": 150000.0}


def _fix(s: str, args: tuple) -> list[dict]:
    """Маршрутизация фикстур по узнаваемым фрагментам финального SQL (одна строка, пробелы схлопнуты).

    Порядок проверок: сверху вниз; верхние — специфичные, пересечений между проверками нет.
    """
    # ── заказы / досье ──
    if "FROM orders WHERE order_id = %s" in s:                                     # order_full: head (id=1 есть, иного нет → 404)
        return [ORDER_HEAD] if args and args[0] == 1 else []
    if "FROM order_items WHERE orders_id = %s" in s:                               # order_full: items
        return [ORDER_ITEM]
    if "FROM demand_items WHERE orders_id" in s:                                   # order_full: demand_items
        return [DEMAND_ITEM]
    if "FROM shipments WHERE orders_id" in s:                                      # order_full: shipments
        return [SHIPMENT]
    if "FROM sales WHERE orders_id" in s:                                          # order_full: sales
        return [SALE]
    if "FROM order_status_history WHERE" in s:                                     # order_full: история статусов
        return [STATUS_HIST]
    # ── сводка / дашборд ──
    if "MAX(detail_fetched_at)" in s:                                              # sync/status: data_as_of
        return [{"max": "2026-09-29 10:00:00"}]
    if "orders_today" in s:                                                        # /api/kpi
        return [KPI]
    if "WITH done AS" in s:                                                        # /api/leadtime
        return [LEAD]
    if "EXTRACT(month FROM order_date)::int AS m," in s:                           # /api/heatmap (до monthly)
        return [HEAT]
    if "GROUP BY 1,2 ORDER BY 1,2" in s:                                           # /api/monthly
        return [MONTH]
    if "EXTRACT(year FROM order_date)::int AS year" in s:                          # /api/years
        return [YEAR]
    if "contractor_name AS name, COUNT(*)::int AS orders" in s:                    # /api/top/contractors
        return [TOP_CONTR]
    if "i.name, SUM(i.quantity)::float8 AS units" in s:                            # /api/top/items
        return [TOP_ITEM]
    if "COALESCE(order_status, '—') AS status" in s:                               # /api/status_breakdown
        return [STATUS]
    if "MAX(order_date)::date AS last_order" in s:                                 # /api/freshness
        return [FRESHNESS]
    if "SELECT COUNT(*)::int AS c FROM orders" in s:                               # /api/orders: счётчик
        return [{"c": 1}]
    if "SELECT id, order_id, number, order_date, order_status, contractor_name, branch_name, sum FROM orders" in s:
        return [ORDER]                                                             # /api/orders: строки
    if "shipment_date, contractor_name, sum FROM orders" in s:                     # /api/export/orders.csv
        return [EXPORT_ORDER]
    if "COUNT(*)::int AS orders, COALESCE(SUM(sum),0)::float8 AS revenue" in s:    # /api/compare (все period)
        return [COMPARE]
    if "AS pct" in s:                                                              # /api/cancel_rate
        return [CANCEL]
    if "AS age_days" in s:                                                         # /api/stale
        return [STALE]
    if "WITH rev AS" in s:                                                         # /api/abc
        return [ABC]
    if "WITH pm AS" in s:                                                          # /api/cohorts: retention
        return [COHORT_RET]
    if "MIN(date_trunc('month', order_date))" in s:                                # /api/cohorts: new_by_month
        return [COHORT_NEW]
    if "COUNT(DISTINCT branch_id_1c)::int AS active_branches" in s:                # /api/cohorts: active_by_month
        return [COHORT_ACT]
    if "FROM orders o LEFT JOIN branches b" in s:                                  # /api/cohorts: top_branches
        return [COHORT_TOP]
    if "SELECT id_1c, name, address, latitude, longitude FROM branches" in s:      # /api/branches
        return [BRANCH]
    # ── каталог ──
    if "FROM catalog_tree_stats" in s:                                             # catalog/tree: снапшот (фаза 3)
        return [dict(r) for r in TREE_STATS]
    if "GROUP BY nf.kind, nf.group_name" in s:                                     # catalog/tree: группы
        return [TREE_GROUP]
    if "GROUP BY nf.kind ORDER BY n_items DESC" in s:                              # catalog/tree: виды
        return [TREE_KIND]
    if "branch_price_stats" in s:                                                  # catalog/branches (сводка)
        return [CAT_BRANCH]
    if "COUNT(DISTINCT p.branch_id_1c)" in s:                                      # catalog/search
        return [CAT_SEARCH]
    if "ORDER BY p.discount_price DESC NULLS LAST" in s:                           # catalog/prices/{id}
        return [CAT_PRICE]
    if "DISTINCT ON (version_date::date, branch_id_1c)" in s:                      # price_history без branch
        return [PRICE_HIST]
    if "AND p.branch_id_1c = %s ORDER BY version_date" in s:                       # price_history с branch
        return [PRICE_HIST]
    if "DISTINCT ON (p2.nomenclature_id)" in s:                                    # catalog/items: строки
        return [CAT_ITEM]
    if "SELECT COUNT(*) AS n FROM ( SELECT DISTINCT p.nomenclature_id" in s:       # catalog/items: счётчик
        return [{"n": 3}]
    if "btrim(nf.surface)" in s:                                                   # catalog/surfaces
        return [SURF]
    # ── склад ──
    if "SELECT DISTINCT snapshot_date::date AS d" in s:                            # remnants/history: даты
        return [{"d": datetime.date(2026, 9, 1)}, {"d": datetime.date(2026, 9, 8)}]
    if "COUNT(DISTINCT nomenclature_id) FROM remnants_snapshots r2" in s:          # history: агрегат по всем
        return [HIST_ALL]
    if "FROM remnants_snapshots WHERE nomenclature_id = %s" in s:                  # history: по товару
        return [HIST_NOM]
    if "SELECT MAX(snapshot_date)::date AS d" in s:                                # remnants: последний снапшот
        return [{"d": datetime.date(2026, 9, 30)}]
    if "FROM remnants_snapshots r LEFT JOIN nomenclature" in s:                    # remnants: строки
        return [REMNANT]
    if "snapshot_date::text AS d" in s:                                            # remnants/dates
        return [{"d": "2026-09-30"}, {"d": "2026-09-29"}]
    # ── карточка товара ──
    if "surface, weight, group_name, kind FROM nomenclature_full" in s:            # card: info
        return [CARD_INFO]
    if "MAX(o.order_date) AS last_order" in s:                                     # card: sold_all
        return [SOLD_ALL]
    if "i.id_1c = %s AND i.kind = 'nomenclature' AND o.order_date >= now() - interval '12 months'" in s:
        return [SOLD12]                                                            # card: sold12
    if "to_char(version_date, 'YYYY-MM-01')" in s:                                 # card: price_history
        return [CARD_PRICE]
    if "AND (r.qty > 0 OR" in s:                                                   # card: remnants
        return [CARD_REM]
    if "i2.orders_id IN" in s:                                                     # card: together
        return [TOGETHER]
    # ── поиск / связи ──
    if "WHERE number ILIKE %s OR contractor_name ILIKE %s" in s:                   # search_all: orders
        return [SR_ORDER]
    if "SELECT id_1c, full_name, color, thickness FROM nomenclature_full" in s:    # search_all: items
        return [SR_ITEM]
    if "COALESCE(n.full_name, n2.name)" in s:                                      # forecast: расход
        return [BURNT]
    if "WHERE kind = 'metall' AND qty > 0" in s:                                   # forecast: остатки
        return [{"nomenclature_id": "N-1", "stock": 100.0}]
    if "a.oid = b.oid" in s:                                                       # basket/pairs
        return [PAIR]
    # ── люди ──
    if "WITH shipped AS (" in s:                                                   # people/summary: итоги
        return [P_SUMMARY]
    if "demand_responsible AS person" in s:                                        # summary:тренд; compare:строки и mrows
        return [P_TREND]
    if "AS pm" in s:                                                               # people/monthly: прошлый год
        return [P_PREV]
    if "AS period" in s:                                                           # people/monthly: график
        return [P_SERIES]
    if "AVG(sum), 0)::float8 AS avg_check" in s:                                   # people/monthly: помесячная
        return [P_CUR]
    if "AS ANY(%s)" in s:                                                          # people/compare (страховка)
        return [P_TREND]
    if "demand_responsible = %s" in s:                                             # (страховка)
        return [P_TREND]
    raise AssertionError("нет фикстуры для SQL: " + s[:300])


class _CurStub:
    def execute(self, *a, **k):
        pass


@pytest.fixture()
def calls() -> list[tuple[str, tuple]]:
    return []


@pytest.fixture()
def client(monkeypatch, calls):
    """TestClient без БД: q/q1 (во всех роут-модулях) и _cur подменены; вызовы журналируются.

    Фаза 2: маршруты каталога живут в web_catalog — патчим ровно реальное место вызова.
    Фаза 5: маршруты склада/заказов живут в web_stock/web_orders — патчим ровно реальные места вызова.
    Фаза 6: маршруты дашборда/синка живут в web_dash/web_sync — патчим ровно реальные места вызова.
    """

    def fake_q(sql, args=()):
        s = " ".join(sql.split())
        calls.append((s, tuple(args)))
        return [copy.deepcopy(r) for r in _fix(s, tuple(args))]

    def fake_q1(sql, args=()):
        rows = fake_q(sql, args)
        return copy.deepcopy(rows[0]) if rows else {}

    def fake_cur():
        return contextlib.nullcontext(_CurStub())

    monkeypatch.setattr(web, "_cur", fake_cur)  # единственный живой потребитель в web — /healthz
    monkeypatch.setattr(web_common, "q", fake_q)
    monkeypatch.setattr(web_common, "q1", fake_q1)
    monkeypatch.setattr(web_catalog, "q", fake_q)
    monkeypatch.setattr(web_catalog, "q1", fake_q1)
    # Фаза 4: маршруты людей живут в web_people — патчим ровно реальное место вызова.
    monkeypatch.setattr(web_people, "q", fake_q)
    # Фаза 5: маршруты склада/заказов живут в web_stock/web_orders — патчим ровно реальные места вызова.
    monkeypatch.setattr(web_stock, "q", fake_q)
    monkeypatch.setattr(web_stock, "q1", fake_q1)
    monkeypatch.setattr(web_orders, "q", fake_q)
    monkeypatch.setattr(web_orders, "q1", fake_q1)
    # Фаза 6: маршруты дашборда/синка живут в web_dash/web_sync — патчим ровно реальные места вызова.
    monkeypatch.setattr(web_dash, "q", fake_q)
    monkeypatch.setattr(web_dash, "q1", fake_q1)
    monkeypatch.setattr(web_sync, "q1", fake_q1)
    # изоляция кэшей процесса между тестами:
    monkeypatch.setattr(web_catalog, "_catalog_tree_cache", {"at": 0.0, "data": None, "etag": None})
    monkeypatch.setattr(web_stock, "_rem_hist_cache", {})
    return TestClient(web.app)


def _ok(c, path):
    r = c.get(path)
    assert r.status_code == 200, (path, r.status_code, r.text[:300])
    return r


# ── (а) Golden-список всех 40 маршрутов ─────────────────────────────────────────────

GOLDEN = {  # 37 × /api/* + /healthz + / + /legacy = 40
    "GET /api/kpi", "GET /api/years", "GET /api/monthly", "GET /api/top/contractors", "GET /api/top/items",
    "GET /api/status_breakdown", "GET /api/freshness", "GET /api/orders", "POST /api/sync",
    "GET /api/sync/status", "GET /api/catalog/search", "GET /api/catalog/prices/{nom_id}",
    "GET /api/catalog/price_history/{nom_id}", "GET /api/catalog/tree", "GET /api/catalog/branches",
    "GET /api/catalog/items", "GET /api/catalog/surfaces", "GET /api/remnants", "GET /api/remnants/dates",
    "GET /api/order/{order_id}/full", "GET /api/compare", "GET /api/leadtime", "GET /api/cancel_rate",
    "GET /api/stale", "GET /api/abc", "GET /api/heatmap", "GET /api/search_all", "GET /api/item/{nom_id}/card",
    "GET /api/remnants/history", "GET /api/export/orders.csv", "GET /api/forecast/remnants",
    "GET /api/basket/pairs", "GET /api/cohorts", "GET /api/branches", "GET /api/people/summary",
    "GET /api/people/monthly", "GET /api/people/compare", "GET /healthz", "GET /", "GET /legacy",
}


def _route_signatures() -> set[str]:
    out = set()
    for r in web.app.routes:
        if isinstance(r, APIRoute):
            for m in sorted(r.methods - {"HEAD", "OPTIONS"}):
                out.add(f"{m} {r.path}")
    return out


def test_golden_40_routes():
    got = _route_signatures()
    missing, extra = GOLDEN - got, got - GOLDEN
    assert not missing and not extra, f"missing={sorted(missing)} extra={sorted(extra)}"


def test_golden_40_count():
    assert len(GOLDEN) == 40
    assert len(_route_signatures()) == 40


# ── (б) Структура ответов (таблица «путь → ожидаемая структура») ────────────────────

def _num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


class TestDash:
    def test_kpi(self, client):
        j = _ok(client, "/api/kpi").json()
        keys = {"orders_today", "orders_30d", "sum_30d", "shipped_30", "avg_30"}
        assert keys <= set(j) and all(_num(j[k]) for k in keys)

    def test_years(self, client):
        rows = _ok(client, "/api/years").json()
        assert isinstance(rows, list) and rows
        assert {"year", "cnt", "revenue", "avg_check", "done_cnt"} <= set(rows[0])

    def test_monthly(self, client):
        rows = _ok(client, "/api/monthly").json()
        assert isinstance(rows, list) and rows
        assert {"year", "month", "cnt", "total", "done_cnt"} <= set(rows[0])

    def test_top_contractors(self, client):
        rows = _ok(client, "/api/top/contractors?limit=3").json()
        assert isinstance(rows, list) and rows
        assert {"name", "orders", "revenue"} <= set(rows[0])

    def test_top_items(self, client):
        rows = _ok(client, "/api/top/items?limit=3").json()
        assert isinstance(rows, list) and rows
        assert {"name", "units", "revenue"} <= set(rows[0])

    def test_status_breakdown(self, client):
        rows = _ok(client, "/api/status_breakdown").json()
        assert isinstance(rows, list) and rows
        assert {"status", "cnt"} <= set(rows[0])

    def test_freshness(self, client):
        j = _ok(client, "/api/freshness").json()
        assert {"last_order", "total", "total_orders"} <= set(j)

    def test_compare_month(self, client):
        rows = _ok(client, "/api/compare?period=month&anchor=2026-09").json()
        assert isinstance(rows, list) and rows
        assert {"orders", "revenue", "avg_check", "canceled", "label", "kind", "prev_orders", "prev_revenue",
                "d_orders", "d_revenue", "p_orders", "p_revenue"} <= set(rows[0])

    def test_leadtime(self, client):
        rows = _ok(client, "/api/leadtime").json()
        assert isinstance(rows, list) and rows
        assert {"label", "median_days", "p90_days", "shipped"} <= set(rows[0])

    def test_cancel_rate(self, client):
        rows = _ok(client, "/api/cancel_rate").json()
        assert isinstance(rows, list) and rows
        assert {"label", "orders", "canceled", "pct"} <= set(rows[0])

    def test_stale(self, client):
        rows = _ok(client, "/api/stale").json()
        assert isinstance(rows, list) and rows
        assert {"order_id", "number", "order_date", "order_status", "contractor_name", "branch_name",
                "sum", "age_days"} <= set(rows[0])

    def test_abc(self, client):
        rows = _ok(client, "/api/abc").json()
        assert isinstance(rows, list) and rows
        assert {"name", "revenue", "units", "share_pct", "cum_share_pct", "abc"} <= set(rows[0])

    def test_abc_cls_A(self, client):
        rows = _ok(client, "/api/abc?cls=A").json()
        assert rows and all(r["abc"] == "A" for r in rows)

    def test_heatmap(self, client):
        j = _ok(client, "/api/heatmap").json()
        assert {"years", "matrix", "metric"} <= set(j)
        assert j["years"]
        assert all(len(j["matrix"][str(y)]) == 12 and all(_num(v) for v in j["matrix"][str(y)])
                   for y in j["years"])  # 12 колонок-месяцев, числа

    def test_cohorts(self, client):
        j = _ok(client, "/api/cohorts").json()
        assert {"new_by_month", "active_by_month", "retention", "top_branches"} <= set(j)

    def test_branches(self, client):
        r = _ok(client, "/api/branches")
        rows = r.json()
        assert isinstance(rows, list) and rows
        assert {"id_1c", "name", "address", "latitude", "longitude"} <= set(rows[0])
        assert r.headers["cache-control"] == "public, max-age=600"  # инвариант мидлвари


class TestOrders:
    def test_orders(self, client):
        j = _ok(client, "/api/orders").json()
        assert {"items", "total", "limit", "offset"} <= set(j)
        assert j["items"] and {"id", "order_id", "number", "order_date", "order_status", "contractor_name",
                               "branch_name", "sum"} <= set(j["items"][0])

    def test_order_full(self, client):
        j = _ok(client, "/api/order/1/full").json()
        assert {"head", "items", "demand_items", "shipments", "sales", "status_history"} <= set(j)

    def test_order_full_404(self, client):
        assert client.get("/api/order/999999/full").status_code == 404

    def test_search_all(self, client):
        j = _ok(client, "/api/search_all?q=Кредо").json()
        assert {"orders", "items"} <= set(j)
        assert j["orders"] and j["items"]
        assert {"order_id", "number", "order_date", "order_status", "contractor_name", "sum"} <= set(j["orders"][0])
        assert {"id_1c", "full_name", "color", "thickness"} <= set(j["items"][0])

    def test_search_all_short_q(self, client, calls):
        j = _ok(client, "/api/search_all?q=1").json()
        assert j == {"orders": [], "items": []}
        assert not calls  # короткий запрос не доходит до БД

    def test_export_orders_csv(self, client):
        r = _ok(client, "/api/export/orders.csv?q=УО")
        assert r.headers["content-type"] == "text/csv; charset=cp1251"
        assert r.headers["content-disposition"] == "attachment; filename=orders.csv"
        head = r.content.split(b"\r\n")[0] if b"\r\n" in r.content else r.content.split(b"\n")[0]
        assert head.decode("utf-8") == "id;номер;дата;статус;отгрузка;контрагент;сумма_заказа"


class TestSync:
    def test_post_sync_200_then_409(self, client, monkeypatch):
        monkeypatch.setattr(web_sync, "_sync_state", {"running": False, "started": None, "finished": None,
                                                 "ok": None, "error": None, "result": None, "traceback": None})
        monkeypatch.setattr(web_sync, "_sync_worker", lambda what="orders": None)  # стаб: running не сбросится
        r1 = client.post("/api/sync")
        assert r1.status_code == 200
        j1 = r1.json()
        assert j1["started"] is True and j1["what"] == "orders" and isinstance(j1["state"], dict)
        r2 = client.post("/api/sync")
        assert r2.status_code == 409

    def test_sync_status(self, client, monkeypatch):
        monkeypatch.setattr(web_sync, "_sync_state", {"running": False, "started": None, "finished": None,
                                                 "ok": None, "error": None, "result": None, "traceback": None})
        j = _ok(client, "/api/sync/status").json()
        assert {"running", "started", "finished", "ok", "error", "result", "traceback",
                "data_as_of"} <= set(j)


class TestCatalog:
    def test_search(self, client):
        rows = _ok(client, "/api/catalog/search?s=Кредо").json()
        assert isinstance(rows, list) and rows
        assert {"id_1c", "full_name", "color", "thickness", "surface", "weight", "group_name",
                "branches"} <= set(rows[0])

    def test_search_too_short_422(self, client):
        assert client.get("/api/catalog/search?s=1").status_code == 422

    def test_prices(self, client):
        rows = _ok(client, "/api/catalog/prices/N-1").json()
        assert isinstance(rows, list) and rows
        assert {"branch_id_1c", "branch", "price", "discount_pct", "discount_price", "version_date"} <= set(rows[0])

    def test_price_history(self, client):
        rows = _ok(client, "/api/catalog/price_history/N-1").json()
        assert isinstance(rows, list) and rows
        assert {"version_date", "branch_id_1c", "branch", "price", "discount_price"} <= set(rows[0])

    def test_price_history_branch(self, client):
        rows = _ok(client, "/api/catalog/price_history/N-1?branch=4d300c12").json()
        assert isinstance(rows, list) and rows
        assert {"version_date", "branch_id_1c", "branch", "price", "discount_price"} <= set(rows[0])

    def test_tree(self, client):
        j = _ok(client, "/api/catalog/tree").json()
        assert "kinds" in j and j["kinds"]
        k = j["kinds"][0]
        assert {"kind", "n_items", "n_families", "families"} <= set(k)
        f = k["families"][0]
        assert {"family", "n_items", "n_priced", "groups"} <= set(f)

    def test_tree_snapshot_200(self, client, calls):
        """Снапшот-путь: значения и порядок ключей ровно как у старого ответа; тяжёлые SQL не дёргаются."""
        r = _ok(client, "/api/catalog/tree")
        assert r.headers["ETag"] == f'W/"{int(TREE_TS.timestamp())}-{len(TREE_STATS)}"'
        k = r.json()["kinds"][0]
        assert (k["kind"], k["n_items"], k["n_families"]) == ("Продукция", 3, 1)
        f = k["families"][0]
        assert (f["family"], f["n_items"], f["n_priced"]) == ("Металлочерепица", 3, 2)
        assert f["groups"] == [{"kind": "Продукция", "group_name": "Металлочерепица Кредо",
                                "n_items": 3, "n_priced": 2}]
        assert [list(g) for g in f["groups"]] == [["kind", "group_name", "n_items", "n_priced"]]
        assert len(calls) == 1 and "FROM catalog_tree_stats" in calls[0][0]

    def test_tree_304_if_none_match(self, client):
        """ETag по версии снапшота (не payload): совпал If-None-Match → 304 без тела."""
        etag = _ok(client, "/api/catalog/tree").headers["ETag"]
        assert etag == f'W/"{int(TREE_TS.timestamp())}-{len(TREE_STATS)}"'
        r = client.get("/api/catalog/tree", headers={"If-None-Match": etag})
        assert r.status_code == 304 and r.content == b"" and r.headers["ETag"] == etag
        # версия сменилась → снова 200:
        r2 = client.get("/api/catalog/tree", headers={"If-None-Match": 'W/"123-1"'})
        assert r2.status_code == 200 and r2.json()["kinds"]

    def test_tree_fallback_stale(self, client, calls, monkeypatch):
        """built_at старше 48ч (2× интервал синка) → старый тяжёлый путь; ETag не выдаётся."""
        stale = TREE_TS - datetime.timedelta(hours=49)
        monkeypatch.setitem(globals(), "TREE_STATS", [dict(r, built_at=stale) for r in TREE_STATS])
        r = _ok(client, "/api/catalog/tree")
        k = r.json()["kinds"][0]
        assert (k["kind"], k["n_items"]) == ("Продукция", 5)  # 5 — из TREE_KIND: это старый путь
        assert "ETag" not in r.headers
        assert len(calls) == 3  # снапшот + 2 тяжёлых SQL

    def test_tree_fallback_empty(self, client, monkeypatch):
        """Пустая таблица снапшота → старый тяжёлый путь, контракт прежний."""
        monkeypatch.setitem(globals(), "TREE_STATS", [])
        j = _ok(client, "/api/catalog/tree").json()
        k = j["kinds"][0]
        assert (k["kind"], k["n_items"]) == ("Продукция", 5)
        f = k["families"][0]
        assert (f["family"], f["n_items"], f["n_priced"]) == ("Металлочерепица", 3, 2)
        assert f["groups"][0]["group_name"] == "Металлочерепица Кредо"

    def test_tree_snapshot_equals_heavy(self, monkeypatch):
        """Контракт байт-в-байт: одни и те же данные → одинаковый JSON обоими путями (+ETag)."""
        groups = [
            {"kind": "Продукция", "group_name": "Металлочерепица Кредо", "n_items": 10, "n_priced": 8},
            {"kind": "Продукция", "group_name": "Металлочерепица Кредо мерная", "n_items": 5, "n_priced": 5},
            {"kind": "Товары", "group_name": "Виниловый сайдинг Vicker", "n_items": 3, "n_priced": 1},
        ]

        def q_heavy(sql, args=()):
            s = " ".join(sql.split())
            if "GROUP BY nf.kind, nf.group_name" in s:
                return copy.deepcopy(groups)
            return [{"kind": "Продукция", "n_items": 15}, {"kind": "Товары", "n_items": 3}]  # = суммы групп

        monkeypatch.setattr(web_catalog, "q", q_heavy)
        heavy = web_catalog._tree_heavy()
        ts = datetime.datetime.now(datetime.timezone.utc)
        kind_totals = {"Продукция": 15, "Товары": 3}  # = суммы групп (как в heavy-фикстуре)
        snap_rows = [dict(g, family=web_common._catalog_family(g["group_name"]),
                          kind_total=kind_totals.get(g["kind"], 0), built_at=ts)
                     for g in copy.deepcopy(groups)]
        monkeypatch.setattr(web_catalog, "q", lambda sql, args=(): [dict(r) for r in snap_rows])
        snap, etag = web_catalog._tree_from_snapshot()
        assert snap == heavy
        # порядок ключей (JSON-байты) — как у старого ответа (SELECT-порядок колонок):
        assert [list(k) for k in snap["kinds"]] == [["kind", "n_items", "n_families", "families"]] * 2
        assert list(snap["kinds"][0]["families"][0]) == ["family", "n_items", "n_priced", "groups"]
        assert list(snap["kinds"][0]["families"][0]["groups"][0]) == ["kind", "group_name", "n_items", "n_priced"]
        assert etag == f'W/"{int(ts.timestamp())}-{len(snap_rows)}"'

    def test_rebuild_catalog_tree_stats(self):
        """Сборщик: 2 тяжёлых SELECT → TRUNCATE+INSERT одной транзакцией; свёртка — общая _catalog_family."""
        results = [
            [("Продукция", 12)],  # kinds (после COALESCE в SQL)
            [("Продукция", "Металлочерепица Кредо", 10, 8), ("Продукция", "—", 2, 0)],  # groups
        ]

        class _Cur:
            def __init__(self):
                self.exec_ = []

            def execute(self, sql, args=None):
                self.exec_.append((sql, args))

            def executemany(self, sql, seq):
                self.exec_.append((sql, [tuple(r) for r in seq]))

            def fetchall(self):
                return results.pop(0) if results else []

            def close(self):
                pass

        class _Conn:
            def __init__(self):
                self.cur = _Cur()
                self.commits = 0

            def cursor(self):
                return self.cur

            def commit(self):
                self.commits += 1

        conn = _Conn()
        n = catalog_tree_build.rebuild_catalog_tree_stats(conn)
        assert n == 2 and conn.commits == 1
        texts = [e[0] for e in conn.cur.exec_]
        assert "FROM nomenclature_full" in texts[0] and "FROM nomenclature_full" in texts[1]
        assert "LEFT JOIN prices_history" in texts[1]
        assert texts[2] == "TRUNCATE catalog_tree_stats"
        assert texts[3].startswith("INSERT INTO catalog_tree_stats")
        # свёртка семейств — общая _catalog_family ('—' в том-числе для без-групповых, как COALESCE в SQL):
        assert conn.cur.exec_[3][1] == [
            ("Продукция", "Металлочерепица", "Металлочерепица Кредо", 10, 8, 12),
            ("Продукция", "—", "—", 2, 0, 12),
        ]

    def test_catalog_branches(self, client):
        rows = _ok(client, "/api/catalog/branches").json()
        assert isinstance(rows, list) and rows
        assert {"id_1c", "name", "n_items"} <= set(rows[0])

    def test_items(self, client):
        j = _ok(client, "/api/catalog/items?branch=4d300c12").json()
        assert {"total", "items"} <= set(j)
        assert j["total"] == 3 and j["items"]
        assert {"id_1c", "code_1c", "full_name", "group_name", "color", "thickness", "surface", "price",
                "discount_pct", "discount_price", "version_date"} <= set(j["items"][0])

    def test_items_empty_branch(self, client, calls):
        j = _ok(client, "/api/catalog/items?branch=").json()
        assert j == {"total": 0, "items": []}
        assert not calls  # без branch SQL не выполняется вовсе

    def test_surfaces(self, client):
        j = _ok(client, "/api/catalog/surfaces?branch=4d300c12&group=Металлочерепица Кредо").json()
        assert {"group", "total", "surfaces"} <= set(j)
        assert j["surfaces"] and {"surface", "n"} <= set(j["surfaces"][0])
        assert j["surfaces"][0]["surface"] == "Полиэстер"  # «Полиэстер матовый» → «Полиэстер»

    def test_item_card(self, client):
        j = _ok(client, "/api/item/N-1/card").json()
        assert {"info", "sold_all", "sold12", "price_history", "remnants", "together"} <= set(j)


class TestStock:
    def test_remnants(self, client):
        rows = _ok(client, "/api/remnants").json()
        assert isinstance(rows, list) and rows
        assert {"nomenclature_id", "full_name", "storage_id", "branch", "qty", "delivery_date",
                "snapshot_date"} <= set(rows[0])

    def test_remnants_dates(self, client):
        j = _ok(client, "/api/remnants/dates").json()
        assert "dates" in j and j["dates"] and all(isinstance(d, str) for d in j["dates"])

    def test_remnants_history(self, client):
        j = _ok(client, "/api/remnants/history").json()
        assert "dates" in j and "series" in j
        s = j["series"]["metall"]
        assert s and {"date", "qty", "items"} <= set(s[0])

    def test_forecast(self, client):
        j = _ok(client, "/api/forecast/remnants").json()
        assert {"days", "rows"} <= set(j)
        row = j["rows"][0]
        assert {"id_1c", "name", "spent", "rate_day", "stock", "days_left", "orders_cnt", "flag"} <= set(row)
        assert row["flag"] in ("crit", "warn", "ok")

    def test_basket_pairs(self, client):
        j = _ok(client, "/api/basket/pairs").json()
        assert "pairs" in j and j["pairs"]
        assert {"a_name", "b_name", "cnt"} <= set(j["pairs"][0])


class TestPeople:
    def test_people_summary(self, client):
        j = _ok(client, "/api/people/summary").json()
        assert {"period_months", "summary", "by_month", "by_day"} <= set(j)
        assert j["summary"] and {"person", "deals_total", "revenue_mln", "deals_per_month",
                                 "avg_month_revenue_mln", "first_month"} <= set(j["summary"][0])

    def test_people_monthly(self, client):
        j = _ok(client, "/api/people/monthly?person=Иван&months=24").json()
        assert {"person", "months", "gran", "series", "monthly", "prev_year_same_month"} <= set(j)
        assert j["gran"] in ("day", "week", "month")

    def test_people_compare(self, client):
        j = _ok(client, "/api/people/compare?people=Иван;Мария").json()
        assert {"gran", "months", "series", "months_monthly", "series_monthly"} <= set(j)
        assert j["gran"] in ("day", "week", "month")


# ── (в) Клэмпы: без БД — проверяем фактический SQL, ушедший в q/q1 ──────────────────

def _sql_of(calls, marker):
    hits = [s for s, _ in calls if marker in s]
    assert hits, (marker, [s[:120] for s, _ in calls])
    return hits


class TestClamps:
    def test_limit_9999_to_200_orders(self, client, calls):
        _ok(client, "/api/orders?limit=9999")
        rows_args = [a for s, a in calls if "SELECT id, order_id, number" in s]
        assert (200, 0) in rows_args  # LIMIT %s OFFSET %s ← limit=200

    def test_limit_9999_to_200_catalog_items(self, client, calls):
        _ok(client, "/api/catalog/items?branch=4d300c12&limit=9999&offset=7")
        rows = _sql_of(calls, "DISTINCT ON (p2.nomenclature_id)")
        assert any("LIMIT 200 OFFSET 7" in s for s in rows)

    def test_months_0_to_1_monthly(self, client, calls):
        _ok(client, "/api/monthly?months=0")
        assert any("interval '1 months'" in s for s, _ in calls)

    def test_months_999_to_120_leadtime(self, client, calls):
        _ok(client, "/api/leadtime?months=999")
        assert any("interval '120 months'" in s for s, _ in calls)

    def test_months_999_to_120_people_summary(self, client, calls):
        _ok(client, "/api/people/summary?months=999")
        assert any("(120 || ' months')" in s for s, _ in calls)

    def test_steps_0_to_1_compare(self, client, calls):
        rows = _ok(client, "/api/compare?period=month&anchor=2026-09&steps=0").json()
        n_calls = sum(1 for s, _ in calls if "COUNT(*)::int AS orders, COALESCE(SUM(sum),0)" in s)
        # steps=0 → клэмп 1 → роут возвращает steps+1 = 2 периода (текущий + 1 назад)
        assert len(rows) == 2 and n_calls == 2

    def test_steps_999_to_5_compare(self, client, calls):
        rows = _ok(client, "/api/compare?period=month&anchor=2026-09&steps=999").json()
        n_calls = sum(1 for s, _ in calls if "COUNT(*)::int AS orders, COALESCE(SUM(sum),0)" in s)
        assert len(rows) == 6 and n_calls == 6  # steps=999 → 5 → 5+1 периодов


# ── (г) Прочее: SPA-страницы и healthz (без БД) ─────────────────────────────────────

class TestSPA:
    def test_root_html(self, client):
        r = _ok(client, "/")
        assert "text/html" in r.headers["content-type"] and "<html" in r.text

    def test_legacy_html(self, client):
        r = _ok(client, "/legacy")
        assert "text/html" in r.headers["content-type"] and "<html" in r.text

    def test_healthz(self, client):
        j = _ok(client, "/healthz").json()
        assert j["ok"] is True and {"used", "conns"} <= set(j["pool"])
