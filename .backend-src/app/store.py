"""Запись в Postgres: upsert заказов, REPLACEMENT позиции, срезы статусов, словари.

Правила:
- Одна транзакция на весь синк-пакет; по ошибке — целиком rollback, sync_log ставит ошибку.
- COALESCE-обновление orders: list-обновление НЕ затирает поля, которые пока дала только detail
  (и наоборот), кроме случаев, когда новая сторона-источник реально даёт не-NULL значение.
- Позиции (order_items/demand_items): DELETE+INSERT в той же транзакции (замещение целиком).
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

import psycopg2
import psycopg2.extras

import config
import normalize as nz

log = logging.getLogger(__name__)

# Поля orders: (колонка, парсер). Один кортеж = один источник.
# "l" — из списка, "d" — из деталей, "b" — из обоих (деталь приоритетнее: обновляет только если не-NULL).
_LIST_COLS = {
    "order_id":                  ("order_id", nz.num),
    "id_1c":                     ("order_id_1c", nz.text),
    "number":                    ("order_code_1c", nz.text),
    "order_date":                ("order_date", nz.dt),
    "ordered_date":              ("ordered_date", nz.dt),
    "order_status":              ("order_status", nz.text),
    "payment_status":            ("order_payment_status", nz.text),
    "sale_status":               ("order_sale_status", nz.text),
    "client_confirm_state":      ("client_confirm_state", nz.text),
    "contractor_name":           ("order_contractor", nz.text),
    "contractor_id_1c":          ("order_contractor_id", nz.text),
    "branch_name":               ("order_branch", nz.text),
    "agreement_name":            ("order_agreement_name", nz.text),
    "sum":                       ("order_sum", nz.num),
    "weight":                    ("order_weight", nz.num),
    "planned_shipment_date":     ("order_date_planned_shipment", nz.dt),
    "planned_delivery_date":     ("order_date_planned_delivery", nz.dt),
    "comment":                   ("order_comment", nz.text),
    "demand_id":                 ("demand_id", nz.num),
    "demand_status":             ("demand_status", nz.text),
    "demand_date":               ("demand_date", nz.dt),
    "demand_responsible":        ("demand_responsible", nz.text),
    "is_transport_docs":         ("is_transport_docs", nz.bool01),
}
_DETAIL_ONLY_COLS = {
    "id_1c":                     ("id_1c", nz.text),
    "number":                    ("number", nz.text),
    "order_date":                ("date", nz.dt),
    "order_status":              ("order_status", nz.text),
    "payment_status":            ("payment_status", nz.text),
    "sale_status":               ("sale_status", nz.text),
    "client_confirm_state":      ("client_confirm_state", nz.text),
    "contractor_id_1c":          ("contractor_id_1c", nz.text),
    "contractor_name":           ("contractor_name", nz.text),
    "branch_id_1c":              ("branch", "id_1c"),
    "branch_name":               ("branch", "name"),
    "agreement_id_1c":           ("agreement", "id_1c"),
    "agreement_name":            ("agreement", "name"),
    "additional_agreement_name": ("additional_agreement_name", nz.text),
    "debt_check_method":         ("agreement", "debt_check_method"),
    "supplier_name":             ("supplier_name", nz.text),
    "subcontractor_name":        ("subcontractor_name", nz.text),
    "sum":                       ("sum", nz.num),
    "weight":                    ("weight", nz.num),
    "shipment_date":             ("order_shipment_date", nz.dt),
    "comment":                   ("comment", nz.text),
    "is_ready_for_shipment":     ("is_ready_for_shipment", nz.bool01),
    "is_allow_online_payment":   ("is_allow_online_payment", nz.bool01),
    "has_completed_shipment":    ("has_completed_shipment", nz.bool01),
}
_DEMAND_COLS = {
    "demand_id":                 ("id", nz.num),
    "demand_status":             ("status", nz.text),
    "demand_create_date":        ("create_date", nz.dt),
    "demand_responsible":        ("responsible", nz.text),
    "demand_sum":                ("sum", nz.num),
    "demand_weight":             ("weight", nz.num),
    "demand_delivery_cost":      ("delivery_cost", nz.num),
    "demand_delivery_type":      ("delivery_type", nz.text),
    "demand_is_delivery":        ("is_delivery", nz.bool01),
    "demand_address":            ("address", nz.text),
    "demand_lat":                ("latitude", nz.num),
    "demand_lon":                ("longitude", nz.num),
}

INSERT_ORDER_SQL = """
INSERT INTO orders (
  order_id, id_1c, number, order_date, ordered_date, order_status, payment_status, sale_status,
  client_confirm_state, contractor_id_1c, contractor_name, branch_id_1c, branch_name,
  agreement_id_1c, agreement_name, additional_agreement_name, debt_check_method,
  supplier_name, subcontractor_name, sum, weight,
  planned_shipment_date, planned_delivery_date, shipment_date, comment,
  demand_id, demand_status, demand_date, demand_create_date, demand_responsible,
  demand_sum, demand_weight, demand_delivery_cost, demand_delivery_type, demand_is_delivery,
  demand_address, demand_lat, demand_lon,
  is_ready_for_shipment, is_transport_docs, is_allow_online_payment, has_completed_shipment,
  detail_hash, detail_fetched_at, list_sig, source, raw_detail, raw_list, fetched_at)
VALUES (
  %(order_id)s, %(id_1c)s, %(number)s, %(order_date)s, %(ordered_date)s, %(order_status)s,
  %(payment_status)s, %(sale_status)s, %(client_confirm_state)s, %(contractor_id_1c)s,
  %(contractor_name)s, %(branch_id_1c)s, %(branch_name)s, %(agreement_id_1c)s, %(agreement_name)s,
  %(additional_agreement_name)s, %(debt_check_method)s, %(supplier_name)s, %(subcontractor_name)s,
  %(sum)s, %(weight)s, %(planned_shipment_date)s, %(planned_delivery_date)s, %(shipment_date)s,
  %(comment)s, %(demand_id)s, %(demand_status)s, %(demand_date)s, %(demand_create_date)s,
  %(demand_responsible)s, %(demand_sum)s, %(demand_weight)s, %(demand_delivery_cost)s,
  %(demand_delivery_type)s, %(demand_is_delivery)s, %(demand_address)s, %(demand_lat)s, %(demand_lon)s,
  %(is_ready_for_shipment)s, %(is_transport_docs)s, %(is_allow_online_payment)s,
  %(has_completed_shipment)s, %(detail_hash)s, CASE WHEN %(detail_hash)s IS NULL THEN NULL ELSE now() END, %(list_sig)s, %(source)s, %(raw_detail)s,
  %(raw_list)s, now())
ON CONFLICT (order_id, id_1c) DO UPDATE SET
  order_id = COALESCE(EXCLUDED.order_id, orders.order_id),
  id_1c = COALESCE(EXCLUDED.id_1c, orders.id_1c),
  number = COALESCE(EXCLUDED.number, orders.number),
  order_date = COALESCE(EXCLUDED.order_date, orders.order_date),
  ordered_date = COALESCE(EXCLUDED.ordered_date, orders.ordered_date),
  order_status = COALESCE(EXCLUDED.order_status, orders.order_status),
  payment_status = COALESCE(EXCLUDED.payment_status, orders.payment_status),
  sale_status = COALESCE(EXCLUDED.sale_status, orders.sale_status),
  client_confirm_state = COALESCE(EXCLUDED.client_confirm_state, orders.client_confirm_state),
  contractor_id_1c = COALESCE(EXCLUDED.contractor_id_1c, orders.contractor_id_1c),
  contractor_name = COALESCE(EXCLUDED.contractor_name, orders.contractor_name),
  branch_id_1c = COALESCE(EXCLUDED.branch_id_1c, orders.branch_id_1c),
  branch_name = COALESCE(EXCLUDED.branch_name, orders.branch_name),
  agreement_id_1c = COALESCE(EXCLUDED.agreement_id_1c, orders.agreement_id_1c),
  agreement_name = COALESCE(EXCLUDED.agreement_name, orders.agreement_name),
  additional_agreement_name = COALESCE(EXCLUDED.additional_agreement_name, orders.additional_agreement_name),
  debt_check_method = COALESCE(EXCLUDED.debt_check_method, orders.debt_check_method),
  supplier_name = COALESCE(EXCLUDED.supplier_name, orders.supplier_name),
  subcontractor_name = COALESCE(EXCLUDED.subcontractor_name, orders.subcontractor_name),
  sum = COALESCE(EXCLUDED.sum, orders.sum),
  weight = COALESCE(EXCLUDED.weight, orders.weight),
  planned_shipment_date = COALESCE(EXCLUDED.planned_shipment_date, orders.planned_shipment_date),
  planned_delivery_date = COALESCE(EXCLUDED.planned_delivery_date, orders.planned_delivery_date),
  shipment_date = COALESCE(EXCLUDED.shipment_date, orders.shipment_date),
  comment = COALESCE(EXCLUDED.comment, orders.comment),
  demand_id = COALESCE(EXCLUDED.demand_id, orders.demand_id),
  demand_status = COALESCE(EXCLUDED.demand_status, orders.demand_status),
  demand_date = COALESCE(EXCLUDED.demand_date, orders.demand_date),
  demand_create_date = COALESCE(EXCLUDED.demand_create_date, orders.demand_create_date),
  demand_responsible = COALESCE(EXCLUDED.demand_responsible, orders.demand_responsible),
  demand_sum = COALESCE(EXCLUDED.demand_sum, orders.demand_sum),
  demand_weight = COALESCE(EXCLUDED.demand_weight, orders.demand_weight),
  demand_delivery_cost = COALESCE(EXCLUDED.demand_delivery_cost, orders.demand_delivery_cost),
  demand_delivery_type = COALESCE(EXCLUDED.demand_delivery_type, orders.demand_delivery_type),
  demand_is_delivery = COALESCE(EXCLUDED.demand_is_delivery, orders.demand_is_delivery),
  demand_address = COALESCE(EXCLUDED.demand_address, orders.demand_address),
  demand_lat = COALESCE(EXCLUDED.demand_lat, orders.demand_lat),
  demand_lon = COALESCE(EXCLUDED.demand_lon, orders.demand_lon),
  is_ready_for_shipment = COALESCE(EXCLUDED.is_ready_for_shipment, orders.is_ready_for_shipment),
  is_transport_docs = COALESCE(EXCLUDED.is_transport_docs, orders.is_transport_docs),
  is_allow_online_payment = COALESCE(EXCLUDED.is_allow_online_payment, orders.is_allow_online_payment),
  has_completed_shipment = COALESCE(EXCLUDED.has_completed_shipment, orders.has_completed_shipment),
  detail_hash = COALESCE(EXCLUDED.detail_hash, orders.detail_hash),
  detail_fetched_at = CASE WHEN EXCLUDED.detail_hash IS NOT NULL THEN COALESCE(orders.detail_fetched_at, now()) ELSE orders.detail_fetched_at END,
  list_sig = COALESCE(EXCLUDED.list_sig, orders.list_sig),
  raw_detail = COALESCE(EXCLUDED.raw_detail, orders.raw_detail),
  raw_list = COALESCE(EXCLUDED.raw_list, orders.raw_list),
  source = EXCLUDED.source,
  fetched_at = now()
RETURNING id;
"""


def _extract(detail_map: dict, row: dict[str, Any]) -> Any:
    """detail_map-значение: (ключ, парсер) — или ('branch', 'name') для вложенных dict."""
    key, second = (detail_map[0], detail_map[1]) if len(detail_map) == 2 else (detail_map, None)
    if second is not None and isinstance(second, str) and key in ("branch", "agreement"):
        # (table, field) форма: значение берём из вложенного dict
        sub = row.get(key) or {}
        if not isinstance(sub, dict):
            return None
        field_map = {"id_1c": nz.text, "name": nz.text, "debt_check_method": nz.text}
        return field_map[second](sub.get(second))
    parser = second if callable(second) else nz.text
    return parser(row.get(key))


def build_order_payload(row: dict[str, Any], *, detail: dict | None = None, source: str) -> dict[str, Any]:
    """Единый payload для INSERT/UPSERT. row — запись списка ИЛИ деталей.

    Detail-поля, не приходящие из списка (id_1c, contractor_id_1c, branch_id_1c, ...), тут NULL,
    если детали нет: при последующем COALESCE-обновлении деталь их доставит.
    """
    p: dict[str, Any] = {k: None for k in (
        "order_id", "id_1c", "number", "order_date", "ordered_date", "order_status", "payment_status",
        "sale_status", "client_confirm_state", "contractor_id_1c", "contractor_name", "branch_id_1c",
        "branch_name", "agreement_id_1c", "agreement_name", "additional_agreement_name",
        "debt_check_method", "supplier_name", "subcontractor_name", "sum", "weight",
        "planned_shipment_date", "planned_delivery_date", "shipment_date", "comment",
        "demand_id", "demand_status", "demand_date", "demand_create_date", "demand_responsible",
        "demand_sum", "demand_weight", "demand_delivery_cost", "demand_delivery_type",
        "demand_is_delivery", "demand_address", "demand_lat", "demand_lon",
        "is_ready_for_shipment", "is_transport_docs", "is_allow_online_payment",
        "has_completed_shipment", "detail_hash", "list_sig", "raw_detail", "raw_list",
    )}

    # -- из списка --
    for col, (row_key, parser) in _LIST_COLS.items():
        p[col] = parser(row.get(row_key))
    p["list_sig"] = nz.list_sig(row)
    p["raw_list"] = nz.jdump(row)

    # -- из деталей (если есть): перекрывают список по не-NULL --
    if detail is not None:
        for col, keypath in _DETAIL_ONLY_COLS.items():
            v = _extract(keypath, detail) if isinstance(keypath, tuple) else keypath[1](detail.get(keypath[0]))
            if v is not None:
                p[col] = v
        demand = detail.get("demand") or {}
        if isinstance(demand, dict):
            for col, keypath in _DEMAND_COLS.items():
                key, parser = keypath
                v = parser(demand.get(key))
                if v is not None:
                    p[col] = v
        # в деталях может не быть planned_shipment_date / comment из списка — их COALESCE сохранит
        for col in ("planned_shipment_date", "planned_delivery_date", "is_transport_docs", "ordered_date"):
            v = p[col]
        p["detail_hash"] = nz.detail_fingerprint(detail)
        p["raw_detail"] = nz.jdump(detail)

    p["source"] = source
    return p


def upsert_order(conn, payload: dict[str, Any]) -> int:
    """Вернуть orders.id (существующий или новый)."""
    cols = list(payload.keys())
    if "source" not in cols:
        raise KeyError("payload must contain 'source'")
    with conn.cursor() as cur:
        cur.execute(INSERT_ORDER_SQL, payload)
        (orders_id,) = cur.fetchone()
    return orders_id


def upsert_dict_rows(conn, table: str, key_col: str, rows: list[tuple[str, Any]]) -> None:
    """Простой upsert справочников (contractors/branches/agreements/nomenclature).

    rows: [(id_1c, другие-поля-кортежем)...] — при разной арности таблиц использует dedicated-функции.
    """
    if not rows:
        return
    queries = {
        "contractors": ("INSERT INTO contractors (id_1c, name) VALUES (%s, %s) "
                        "ON CONFLICT (id_1c) DO UPDATE SET name = EXCLUDED.name, updated_at = now()"),
        "branches":    ("INSERT INTO branches (id_1c, name) VALUES (%s, %s) "
                        "ON CONFLICT (id_1c) DO UPDATE SET name = EXCLUDED.name, updated_at = now()"),
        "agreements":  ("INSERT INTO agreements (id_1c, name, debt_check_method) VALUES (%s, %s, %s) "
                        "ON CONFLICT (id_1c) DO UPDATE SET name = EXCLUDED.name, "
                        "debt_check_method = COALESCE(EXCLUDED.debt_check_method, agreements.debt_check_method), "
                        "updated_at = now()"),
    }
    q = queries.get(table)
    if not q:
        raise ValueError(f"unknown table: {table}")
    with conn.cursor() as cur:
        psycopg2.extras.execute_batch(cur, q, rows)


def replace_items(conn, orders_id: int, table: str, kind: str,
                  items: list[dict[str, Any]], demand_id: int | None = None) -> int:
    """DELETE+INSERT позиций: их состав после последнего обновления деталей актуален целиком."""
    if table not in ("order_items", "demand_items"):
        raise ValueError(table)
    n = 0
    with conn.cursor() as cur:
        cur.execute(f"DELETE FROM {table} WHERE orders_id = %s AND kind = %s", (orders_id, kind))
        for i, it in enumerate(items):
            if not isinstance(it, dict):
                continue
            # API-особенность: услуги приходят с суффиксом Serv (quantityServ/priceServ/totalServ,
            # имя — service_name) и без id_1c/code_1c. Товары — nomenclature_name/quantity/price/totalNom.
            is_svc = kind == "service" or "totalServ" in it
            name = it.get("nomenclature_name") or it.get("service_name") or it.get("descriptionServ")
            unit = (it.get("quantityUnit_name") or it.get("sizeUnit_name") or it.get("amountUnit_name")
                    or (it.get("unitServ") if isinstance(it.get("unitServ"), str) else None))
            qty = it.get("quantity") if it.get("quantity") is not None else it.get("quantityServ")
            price = it.get("price") if it.get("price") is not None else it.get("priceServ")
            disc = it.get("discount") if it.get("discount") is not None else it.get("discountServ")
            dprice = it.get("discountPrice") if it.get("discountPrice") is not None else it.get("discountPriceServ")
            total = it.get("totalNom") or it.get("amount") or it.get("totalServ")
            row = (
                orders_id, demand_id, kind,
                nz.text(it.get("id_1c")), nz.text(it.get("code_1c")), nz.text(name),
                nz.text(it.get("group")), nz.text(unit),
                nz.quantity(qty), nz.num(price), nz.num(disc),
                nz.num(dprice), nz.num(total),
                nz.num(it.get("position", i), 0),
            )
            if table == "order_items":
                cur.execute(
                    "INSERT INTO order_items (orders_id, kind, id_1c, code_1c, name, group_name, unit, "
                    "quantity, price, discount_pct, discount_price, total, position) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (orders_id, kind) + row[3:])
            else:
                cur.execute(
                    "INSERT INTO demand_items (orders_id, demand_id, kind, id_1c, code_1c, name, group_name, "
                    "unit, quantity, price, discount_pct, discount_price, total, position) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", row)
            n += 1
    return n


def upsert_shipments(conn, orders_id: int, shipments: list[dict[str, Any]], source: str) -> int:
    """Отгрузки: не замещаем, а MERGE-им по (orders_id, shipment_number, source)."""
    n = 0
    q = ("INSERT INTO shipments (orders_id, shipment_number, state, driver_name, driver_phone, source) "
         "VALUES (%s, %s, %s, %s, %s, %s) "
         "ON CONFLICT (orders_id, shipment_number, source) DO UPDATE SET "
         "state = COALESCE(EXCLUDED.state, shipments.state), "
         "driver_name = COALESCE(EXCLUDED.driver_name, shipments.driver_name), "
         "driver_phone = COALESCE(EXCLUDED.driver_phone, shipments.driver_phone), "
         "updated_at = now()")
    with conn.cursor() as cur:
        for s in shipments or []:
            if not isinstance(s, dict):
                continue
            cur.execute(q, (orders_id,
                            nz.text(s.get("shipmentNumber") or s.get("number")),
                            nz.text(s.get("shipmentState") or s.get("state")),
                            nz.text(s.get("driverName") or s.get("driver_name")),
                            nz.text(s.get("driverPhones") or s.get("driver_phone")),
                            source))
            n += 1
    return n


def snapshot_order(conn, orders_id: int) -> bool:
    """Ежедневный срез (order_status_history). Пропускает, если сегодня уже снапшотили."""
    today = date.today()
    with conn.cursor() as cur:
        cur.execute("""SELECT order_status, payment_status, sale_status, sum, weight
                       FROM orders WHERE id = %s""", (orders_id,))
        row = cur.fetchone()
        if not row:
            return False
        order_status, payment_status, sale_status, s, w = row
        # терминальные статусы: срез незачем (даты+status в orders уже фиксируют факт отгрузки)
        if order_status in config.SNAPSHOT_EXCLUDE_STATUSES:
            return False
        cur.execute("""INSERT INTO order_status_history
                       (orders_id, snapshot_date, order_status, payment_status, sale_status, sum, weight)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (orders_id, snapshot_date) DO UPDATE SET
                         order_status = EXCLUDED.order_status,
                         payment_status = EXCLUDED.payment_status,
                         sale_status = EXCLUDED.sale_status,
                         sum = EXCLUDED.sum,
                         weight = EXCLUDED.weight,
                         fetched_at = now()""",
                    (orders_id, today, order_status, payment_status, sale_status, s, w))
    return True


def needs_detail(conn, orders_id: int, max_age_hours: int, current_list_sig: str | None = None) -> bool:
    """Деталь нужна, если: никогда не грузилась; ИЛИ устарела (TTL); ИЛИ в списке изменился статус
    (сигнатура разошлась — например, после отгрузки пришла оплата). Терминальные с деталями
    обновляются только при изменении сигнатуры списка."""
    with conn.cursor() as cur:
        cur.execute("""SELECT detail_hash, detail_fetched_at, order_status, list_sig
                       FROM orders WHERE id = %s""", (orders_id,))
        row = cur.fetchone()
    if not row:
        return True
    detail_hash, detail_fetched_at, order_status, stored_sig = row
    if current_list_sig is not None and stored_sig is not None and current_list_sig != stored_sig:
        return True  # список видит изменения (статус/оплата) — деталь надо освежить
    terminal = order_status in ("Машина отгружена", "Отгружен", "Отгружен клиенту")
    if terminal and detail_hash:
        return False
    if detail_hash is None:
        return True
    if detail_fetched_at is None:
        return True
    return detail_fetched_at < datetime.now(timezone.utc) - timedelta(hours=max_age_hours)


def apply_detail(conn, orders_id: int, detail: dict[str, Any], source: str) -> dict[str, int]:
    """Полное применение детали к существующему заказу: поля, позиции, справочники.

    Возвращает counts для sync_log.
    """
    payload = build_order_payload(detail, detail=detail, source=source)
    # КЛЮЧЕВОЙ момент: держим order_id из списка, если деталь его не содержит.
    with conn.cursor() as cur:
        cur.execute("SELECT order_id, contractor_id_1c, branch_id_1c, agreement_id_1c FROM orders WHERE id = %s",
                    (orders_id,))
        row = cur.fetchone()
    if row:
        if not payload.get("order_id"):
            payload["order_id"] = row[0]
        if not payload.get("contractor_id_1c"):
            payload["contractor_id_1c"] = row[1]
        if not payload.get("branch_id_1c"):
            payload["branch_id_1c"] = row[2]
        if not payload.get("agreement_id_1c"):
            payload["agreement_id_1c"] = row[3]

    #Upsert через существующую функцию: конфликтный ключ (order_id, id_1c) совпадает — обновит.
    existing_orders_id = upsert_order(conn, payload)

    counts = {"items": 0, "demand_items": 0, "dicts": 0}

    nomenclatures = detail.get("order_nomenclatures") or []
    services = detail.get("order_services") or []
    counts["items"] = (
        replace_items(conn, existing_orders_id, "order_items", "nomenclature", nomenclatures)
        + replace_items(conn, existing_orders_id, "order_items", "service", services)
    )

    demand = detail.get("demand") or {}
    if isinstance(demand, dict):
        dnd = demand.get("demand_nomenclatures") or []
        dsvc = demand.get("demand_services") or []
        counts["demand_items"] = (
            replace_items(conn, existing_orders_id, "demand_items", "nomenclature", dnd, demand_id=payload.get("demand_id"))
            + replace_items(conn, existing_orders_id, "demand_items", "service", dsvc, demand_id=payload.get("demand_id"))
        )
        # справочники из детали
        contractor = detail.get("contractor_id_1c"), detail.get("contractor_name")
        branch = (detail.get("branch") or {})
        agr = (detail.get("agreement") or {})
        dicts: list[tuple[str, tuple]] = []
        if contractor[0] and contractor[1]:
            dicts.append(("contractors", contractor))
        if branch.get("id_1c") and branch.get("name"):
            dicts.append(("branches", (branch["id_1c"], branch["name"])))
        if agr.get("id_1c") and agr.get("name"):
            dicts.append(("agreements", (agr["id_1c"], agr["name"], agr.get("debt_check_method"))))
        for t, rv in dicts:
            upsert_dict_rows(conn, t, "id_1c", [rv])
        counts["dicts"] = len(dicts)

        # номенклатура-словарь: из позиций заказа и demand
        seen = set()
        for it in (nomenclatures + services + dnd + dsvc):
            if not isinstance(it, dict):
                continue
            key = it.get("id_1c")
            if not key or key in seen:
                continue
            seen.add(key)
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO nomenclature (id_1c, code_1c, name, group_name, unit) VALUES (%s, %s, %s, %s, %s) "
                "ON CONFLICT (id_1c) DO UPDATE SET code_1c = COALESCE(EXCLUDED.code_1c, nomenclature.code_1c), "
                "name = COALESCE(EXCLUDED.name, nomenclature.name), "
                "group_name = COALESCE(EXCLUDED.group_name, nomenclature.group_name), "
                "unit = COALESCE(EXCLUDED.unit, nomenclature.unit), updated_at = now()",
                (key, nz.text(it.get("code_1c")), nz.text(it.get("nomenclature_name")),
                 nz.text(it.get("group")), nz.text(it.get("quantityUnit_name") or it.get("sizeUnit_name"))))
            cur.close()
            counts["dicts"] += 1

    # Отгрузки из деталей (delivery_orders / shipment_processes) — merge
    for key, src in (("delivery_orders", "detail"), ("shipment_processes", "detail")):
        if detail.get(key):
            counts["shipments"] = counts.get("shipments", 0) + upsert_shipments(conn, existing_orders_id, detail[key], src)

    return counts


def start_sync(conn, mode: str) -> int:
    with conn.cursor() as cur:
        cur.execute("INSERT INTO sync_log (mode) VALUES (%s) RETURNING id", (mode,))
        (sid,) = cur.fetchone()
    conn.commit()
    return sid


def finish_sync(conn, sid: int, **counts: Any) -> None:
    cols = ("orders_seen", "details_fetched", "details_skipped", "items_upserted", "errors", "error_detail")
    vals = [counts.get(c) for c in cols]
    set_sql = ", ".join(f"{c} = %s" for c in cols)
    with conn.cursor() as cur:
        cur.execute(f"UPDATE sync_log SET finished_at = now(), {set_sql} WHERE id = %s", (*vals, counts.get("sync_id")))
    conn.commit()


def log_error(conn, sid: int, exc: Exception) -> None:
    """Зафиксировать ошибку; используем finish_sync с errors=1."""
    try:
        finish_sync(conn, sid, errors=1, error_detail=str(exc)[:2000], sync_id=sid)
    except Exception:
        conn.rollback()
        log.exception("не удалось записать sync_log.error")
