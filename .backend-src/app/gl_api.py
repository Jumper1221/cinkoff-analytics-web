"""Клиент GrandLine public API.

Тонкость: при INT-парсинге ключа в строке не теряется; при обрыве соединения
requests сам ретраит только GET через three attempts.
"""
from __future__ import annotations

import logging
import time
from typing import Any

import requests

log = logging.getLogger(__name__)

BASE = "https://client.grandline.ru/api/public"

session = requests.Session()
session.headers.update({"User-Agent": "cinkoff-orders-parser/2.0"})


def _get(path: str, params: dict[str, Any] | None = None, retries: int = 3) -> Any:
    """GET с ретраями и экспоненциальной паузой; поднимает ApiException при 4xx/5xx."""
    url = f"{BASE}/{path.lstrip('/')}"
    for attempt in range(1, retries + 1):
        try:
            resp = session.get(url, params=params, timeout=30)
        except requests.RequestException as exc:
            if attempt == retries:
                raise ApiException(f"сеть: {exc}") from exc
            pause = 2 ** attempt
            log.warning("сеть недоступна (%s), попытка %d/%d через %ds", exc, attempt, retries, pause)
            time.sleep(pause)
            continue
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code in (429, 500, 502, 503, 504) and attempt < retries:
            time.sleep(2 ** attempt)
            continue
        raise ApiException(f"HTTP {resp.status_code} для {url}: {resp.text[:200]}")
    raise ApiException("unreachable")  # pragma: no cover


class ApiException(RuntimeError):
    pass


def fetch_order_list(api_key: str) -> list[dict[str, Any]]:
    """Список последних заказов (без позиций)."""
    data = _get("orders/", params={"api_key": api_key})
    if not isinstance(data, list):
        raise ApiException(f"ожидали список заказов, пришли: {str(data)[:200]}")
    return data


def fetch_order_detail(api_key: str, order_id: int) -> dict[str, Any]:
    """Полная деталь заказа: order_nomenclatures, demand.demand_nomenclatures, packaging и т.д."""
    data = _get(f"orders/{order_id}/", params={"api_key": api_key})
    if not isinstance(data, dict):
        raise ApiException(f"ожидали dict-деталь, пришло: {str(data)[:200]}")
    return data
