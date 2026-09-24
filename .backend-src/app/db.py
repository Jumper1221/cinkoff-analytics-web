"""Подключение к Postgres + применение схемы.

psycopg2 (синхронно, нам хватает); autocommit-DSQL-режим не нужен, пишем транзакциями.
"""
from __future__ import annotations

import logging
from pathlib import Path

import psycopg2
import psycopg2.extras

import config

log = logging.getLogger(__name__)

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def connect() -> psycopg2.extensions.connection:
    conn = psycopg2.connect(
        host=config.PG_HOST, port=config.PG_PORT, dbname=config.PG_DB,
        user=config.PG_USER, password=config.PG_PASSWORD,
        connect_timeout=10, application_name="cinkoff-parser",
    )
    conn.autocommit = False
    with conn.cursor() as cur:
        cur.execute("SET TIME ZONE 'Europe/Moscow'")
        cur.execute("SET extra_float_digits = 3")
    return conn


def ensure_schema(conn: psycopg2.extensions.connection) -> None:
    """Идемпотентно применить schema.sql (все объекты IF NOT EXISTS)."""
    with conn.cursor() as cur:
        cur.execute(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.commit()
    log.info("schema ok")


def register_jsonb(conn: psycopg2.extensions.connection) -> None:
    psycopg2.extras.register_default_jsonb(globally=True, loads=lambda s: s)
