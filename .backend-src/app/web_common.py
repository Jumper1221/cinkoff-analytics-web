"""Общая база веб-слоя: PG-конфиг, пул (+pool_stats), _cur/q/q1, SNAP, CATALOG_KINDS, клэмп-хелперы.

Фаза 1 рефакторинга (docs/REFACTOR_PLAN.md): чистое перемещение из web.py, логика без изменений.
Запускается только из web.py (после его sys.path-шапки) — импортирует через web_common.
"""
from __future__ import annotations

import os
from contextlib import contextmanager

import psycopg2
import psycopg2.extras
from psycopg2.pool import SimpleConnectionPool

PG = dict(
    host=os.getenv("PG_HOST", "localhost"),
    port=int(os.getenv("PG_PORT", "5432")),
    dbname=os.getenv("PG_DB", "orders"),
    user=os.getenv("PG_USER", "orders"),
    password=os.getenv("PG_PASSWORD", "orders_password_change_me"),
    connect_timeout=5,
)

_pool: SimpleConnectionPool | None = None


def _pool_get() -> SimpleConnectionPool:
    global _pool
    if _pool is None:
        _pool = SimpleConnectionPool(2, 10, **PG)
    return _pool


def pool_stats() -> dict:
    """Публичный срез состояния пула (единственное место, знающее приватные поля).

    Фаза 7 (docs/REFACTOR_PLAN.md): /healthz больше не лезет в _pool._used/_pool._pool.
    """
    return {
        "used": len(_pool._used) if _pool else 0,
        "conns": len(_pool._pool) if _pool else 0,
    }


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


SNAP = "order_status IN ('Машина отгружена', 'Отгружен')"

CATALOG_KINDS = ("Продукция", "Товары")


def _catalog_family(group_name: str) -> str:
    """Семейство (2-й уровень дерева): свёртка плоских групп 1С по общему префиксу.

    «Металлочерепица Кредо» и «Металлочерепица Кредо мерная» → «Металлочерепица».
    Пара семейств сворачивается по 2 словам (Виниловый сайдинг/водосток, Виниловый сайдинг Vicker...).

    Фаза 3: единственное общее место свёртки — импортируют web_catalog.catalog_tree (фолбэк)
    и catalog_tree_build (сборщик снапшота); детерминированная, логика без изменений.
    """
    n = " ".join((group_name or "").split())
    if not n:
        return "—"
    words = n.split()
    if words[0] == "Виниловый" and len(words) > 1:
        return "Виниловый " + words[1] if words[1] != "водосток" else "Виниловый водосток"
    if words[0] == "Виниловый":
        return "Виниловый сайдинг"
    return words[0]


# ── Клэмп-хелперы (перенесены из инлайн-клэмпов web.py; имена сохранены) ─────────

def lim(v: int, lo: int = 1, hi: int = 200) -> int:
    """Общая-заготовка-клэмпа-лимита: по-умолчанию 1..200 (orders 197, catalog/items 453); частные диапазоны — параметрами."""
    return max(lo, min(hi, v))


def offset(v: int) -> int:
    """Offset-не-ниже-нуля (catalog/items 454)."""
    return max(0, v)


def months(v: int) -> int:
    """Окно-в-месяцах: 1..120 (monthly 138, leadtime 727, people_* 1169...)."""
    return max(1, min(120, v))


def days(v: int) -> int:
    """Окно-в-днях: 30..3650 (top/contractors 153, top/items 166, status_breakdown 178)."""
    return max(30, min(3650, v))
