"""Нормализация строк из API к типам, готовым для вставки.

API присылает: даты-строки ("2025-12-12T17:54:02+03:00", с 'Z' и с millis),
числа-строки ("2091.52"), "28.000" для количеств, None там, где ждёшь число.
Единственное место, где это разворачивается — здесь.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

_NUM_CLEAN = re.compile(r"[\s\u00a0]")


def dt(value: Any) -> "datetime | None":
    """ISO-строка (с Z, с millis, с +03:00) -> aware-UTC datetime; None/'' -> None."""
    if not value or not isinstance(value, str):
        return None
    s = value.strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    # 2025-12-12T17:50:12.883+03:00 — millis (3 знака).isoformat() в psycopg2 ок, но единообразно до 6:
    m = re.match(r"^(.*T\d{2}:\d{2}:\d{2})\.(\d{1,6})([+-]\d{2}:\d{2})$", s)
    if m:
        frac = (m.group(2) + "000000")[:6]
        s = f"{m.group(1)}.{frac}{m.group(3)}"
    try:
        d = datetime.fromisoformat(s)
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc)


def num(value: Any, ndigits: int = 2) -> "float | None":
    """'2091.52' / '28.000' / 2091 / None -> float|None. Плохая строка -> None, не исключение."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return round(float(value), ndigits)
    s = _NUM_CLEAN.sub("", str(value)).replace(",", ".")
    try:
        return round(float(s), ndigits)
    except ValueError:
        return None


def quantity(value: Any) -> "float | None":
    """Количество: '28.000' -> 28.0; дробное хранится с 3 знаками."""
    return num(value, 3)


def text(value: Any) -> "str | None":
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def bool01(value: Any) -> "bool | None":
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    return str(value).lower() in ("1", "true", "yes", "да", "истина")


def jdump(value: Any) -> "str | None":
    """Компактный JSON для JSONB-полей (psycopg2 кладёт строку как есть при loads=identity)."""
    if value is None:
        return None
    try:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        return None


def detail_fingerprint(detail: dict[str, Any]) -> str:
    """SHA256 по "умному" подмножеству детали: всё, что фактически важно, без волатильного.

    Исключаем: даты версии (version_date, даты-загрузки), списки printForms-флагов
    (они могли варьироваться), 1С-гуиды, кто не влияет на экономику.
    """
    core = {
        "sum": detail.get("sum"),
        "status": detail.get("order_status"),
        "payment": detail.get("payment_status"),
        "sale": detail.get("sale_status"),
        "shipment_date": detail.get("order_shipment_date"),
        "items": sorted(
            (i.get("id_1c") or "", i.get("quantity"), i.get("price"), i.get("discountPrice"), i.get("totalNom"))
            for i in (detail.get("order_nomenclatures") or [])
        ),
        "services": sorted(
            (i.get("id_1c") or "", i.get("quantityServ") or i.get("quantity"),
             i.get("priceServ") or i.get("price"), i.get("totalServ") or i.get("totalNom"))
            for i in (detail.get("order_services") or [])
        ),
        "demand_sum": (detail.get("demand") or {}).get("sum"),
        "demand_items": sorted(
            (i.get("id_1c") or "", i.get("quantity"), i.get("price"))
            for i in ((detail.get("demand") or {}).get("demand_nomenclatures") or [])
        ),
    }
    blob = json.dumps(core, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def list_sig(row: dict[str, Any]) -> str:
    """Сигнатура волатильных полей списка: поймать изменения статуса/оплаты без деталей."""
    core = {
        k: row.get(k)
        for k in ("order_status", "payment_status", "order_sale_status", "order_sum",
                  "order_weight", "order_payment_status", "is_transport_docs", "client_confirm_state")
    }
    blob = json.dumps(core, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
