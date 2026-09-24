"""Точка входа.

- по умолчанию: шедулер — ежедневно 04:30 МСК (и страховка в 12:00): полный sync
- python main.py once          — один sync и выход (тест/ручной запуск)
- python main.py backfill      — разовая заливка исторических дампов из data/
- python main.py enrich N      — догрузить детали N заказам, у которых их нет
"""
from __future__ import annotations

import logging
import os
import sys

from apscheduler.schedulers.blocking import BlockingScheduler

import config
import db
import sync as syncmod

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("cinkoff")


def _conn():
    conn = db.connect()
    db.ensure_schema(conn)
    return conn


def run_sync() -> None:
    if not config.API_KEY:
        log.error("API_KEY не задан — синк невозможен")
        return
    conn = _conn()
    try:
        counts = syncmod.sync(conn, config.API_KEY, with_details=True)
        log.info("SYNC RESULT: %s", counts)
    finally:
        conn.close()


def run_backfill() -> None:
    conn = _conn()
    try:
        counts = syncmod.backfill(conn, dumps_dir=os.getenv("DUMPS_DIR", "/app/data"))
        log.info("BACKFILL RESULT: %s", counts)
    finally:
        conn.close()


def run_enrich(limit: int) -> None:
    if not config.API_KEY:
        log.error("API_KEY не задан — enrich невозможен")
        return
    conn = _conn()
    try:
        counts = syncmod.enrich(conn, config.API_KEY, limit=limit)
        log.info("ENRICH RESULT: %s", counts)
    finally:
        conn.close()


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""

    if cmd == "once":
        run_sync()
    elif cmd == "backfill":
        run_backfill()
    elif cmd == "enrich":
        limit = int(sys.argv[2]) if len(sys.argv) > 2 else 100
        run_enrich(limit)
    else:
        scheduler = BlockingScheduler(timezone="Europe/Moscow")
        scheduler.add_job(run_sync, "cron", hour=4, minute=30, id="daily_sync")
        # страховка: если ночной прогон не случился — второй шанс в 12:00 (всё идемпотентно)
        scheduler.add_job(run_sync, "cron", hour=12, minute=0, id="midday_retry")
        log.info("scheduler: daily_sync 04:30 + midday_retry 12:00 (Europe/Moscow). Ctrl+C — выход.")
        try:
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            log.info("остановлено")


if __name__ == "__main__":
    main()
