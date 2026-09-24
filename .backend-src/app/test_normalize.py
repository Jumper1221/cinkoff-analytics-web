"""Юнит-тесты нормализации (без сети и БД). Запуск: python -m pytest test_normalize.py -q"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

import normalize as nz


def test_dt_variants():
    # +03:00 -> UTC
    assert nz.dt("2025-12-12T17:54:02+03:00") == datetime(2025, 12, 12, 14, 54, 2, tzinfo=timezone.utc)
    # Z-суффикс
    assert nz.dt("2025-12-12T14:50:12.883Z") == datetime(2025, 12, 12, 14, 50, 12, 883000, tzinfo=timezone.utc)
    # millis + offset (как в demand_date)
    assert nz.dt("2025-12-12T17:50:12.883+03:00") == datetime(2025, 12, 12, 14, 50, 12, 883000, tzinfo=timezone.utc)
    # мусор/пусто/None
    assert nz.dt(None) is None
    assert nz.dt("") is None
    assert nz.dt("не-дата") is None
    assert nz.dt(123) is None


def test_num_variants():
    assert nz.num("2091.52") == 2091.52
    assert nz.num("2 091.52") == 2091.52            # неразрывный пробел
    assert nz.num("28.000", 3) == 28.0
    assert nz.num("1,5") == 1.5                     # запятая как разделитель
    assert nz.num(42) == 42.0
    assert nz.num(None) is None
    assert nz.num("") is None
    assert nz.num("абв") is None                    # плохая строка -> None, не исключение


def test_text_bool01():
    assert nz.text("  ") is None
    assert nz.text(" x ") == "x"
    assert nz.bool01(True) is True
    assert nz.bool01("false") is False
    assert nz.bool01(None) is None
    assert nz.bool01("") is None


def test_list_sig_stable_and_sensitive():
    a = {"order_status": "Готов к отгрузке", "order_sum": "100.00", "order_payment_status": "Не оплачен"}
    b = {"order_status": "Готов к отгрузке", "order_sum": "100.00", "order_payment_status": "Не оплачен"}
    c = {"order_status": "Отгружен", "order_sum": "100.00", "order_payment_status": "Не оплачен"}
    assert nz.list_sig(a) == nz.list_sig(b)
    assert nz.list_sig(a) != nz.list_sig(c)


def test_detail_fingerprint_changes_on_price_change():
    d1 = {"order_nomenclatures": [{"id_1c": "x", "quantity": "1", "price": "100", "discountPrice": "100", "totalNom": "100"}]}
    d2 = {"order_nomenclatures": [{"id_1c": "x", "quantity": "1", "price": "110", "discountPrice": "110", "totalNom": "110"}]}
    d3 = {"order_nomenclatures": [{"id_1c": "x", "quantity": "1", "price": "100", "discountPrice": "100", "totalNom": "100"}],
          "version_date": "2026-09-23T13:27:27+03:00"}   # версия даты не влияет
    assert nz.detail_fingerprint(d1) != nz.detail_fingerprint(d2)
    assert nz.detail_fingerprint(d1) == nz.detail_fingerprint(d3)


def test_jdump_non_ascii():
    s = nz.jdump({"name": "Ермолаева"})
    assert "Ермолаева" in s and isinstance(s, str)
