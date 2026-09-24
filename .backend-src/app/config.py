"""Конфиг из окружения (12-factor)."""
from __future__ import annotations

import os
from pathlib import Path

# .env-файл проекта (API_KEY, PG_*): значения НЕ переопределяют уже-заданные-ENV
_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
if _ENV_FILE.exists():
    for _line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
        if "=" in _line and not _line.strip().startswith("#"):
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


API_KEY = os.getenv("API_KEY", "")

# Postgres: собирается из частей или целиком из DATABASE_URL
PG_HOST = os.getenv("PG_HOST", "db")
PG_PORT = _int_env("PG_PORT", 5432)
PG_DB = os.getenv("PG_DB", "orders")
PG_USER = os.getenv("PG_USER", "orders")
PG_PASSWORD = os.getenv("PG_PASSWORD", "")

# Поведение синка
SYNC_DAYS_BACK = _int_env("SYNC_DAYS_BACK", 0)            # 0 = всё, что отдаёт список
MAX_DETAILS_PER_RUN = _int_env("MAX_DETAILS_PER_RUN", 0)  # 0 = без лимита
DETAILS_TTL_DAYS = _int_env("DETAILS_TTL_DAYS", 3)        # раз в сколько дней обновлять деталь заказа
DETAILS_MAX_AGE_H = DETAILS_TTL_DAYS * 24
SNAPSHOT_EXCLUDE_STATUSES = ("Машина отгружена", "Отгружен", "Отгружен клиенту")  # статус больше не меняется
