"""Синк-зона веб-слоя: /api/sync (POST, запуск-синка-в-фоне) + /api/sync/status (пульс+свежесть).

Фаза 6 рефакторинга (docs/REFACTOR_PLAN.md): чистое перемещение из web.py — _sync_worker-тред,
_sync_state, advisory-lock 4242 и импорты db/daily_sync ВНУТРИ функции — как есть, логика без
изменений. Регистрируется в web.py через include_router — пути/параметры дословно как были.
"""
from __future__ import annotations

import threading as _threading
import importlib as _importlib

from fastapi import APIRouter, HTTPException

from web_common import q1

router = APIRouter()

_sync_lock = _threading.Lock()
_sync_state: dict = {"running": False, "started": None, "finished": None,
                     "ok": None, "error": None, "result": None}


def _data_freshness() -> "str | None":
    """Момент-последнего-изменения-данных (для-подписи-«данные-на-…»)."""
    try:
        row = q1("SELECT MAX(detail_fetched_at)::text FROM orders WHERE detail_fetched_at IS NOT NULL")
        return (row or {}).get("max") if isinstance(row, dict) else (row if isinstance(row, str) else None)
    except Exception:
        return None


def _sync_worker(what: str = "orders") -> None:
    """Фоновая-задача: СНАЧАЛА-сырьё-на-диск, ПОТОМ-БД (правило-Михаила).
    Мягкий-замок-БД, чтобы-крон-01:40/09:10-и-кнопка-не-столкнулись:
    второй-ожидающий-тихо-выходит (unlock-плюс-1-мин-страховки)."""
    try:
        import db as _db
        import daily_sync as _ds
        conn = _db.connect()
        _db.ensure_schema(conn)
        try:
            got = conn.execute if False else None  # (напоминание-о-стиле) не-используем
            with conn.cursor() as _c:
                _c.execute("SELECT pg_try_advisory_lock(4242)")
                if not (_c.fetchone() or (False,))[0]:
                    _sync_state.update(running=False, finished=_now_iso(),
                                       ok=True, result={"skipped": "sync-уже-идёт (крон)"})
                    return
            try:
                _ds.sync_orders(conn, days=_ds.INCREMENT_DAYS)
                conn.commit()
                _sync_state["result"] = {"synced": "orders", "window_days": _ds.INCREMENT_DAYS}
            finally:
                with conn.cursor() as _c:
                    _c.execute("SELECT pg_advisory_unlock(4242)")
                    _c.fetchone()
        finally:
            conn.close()
        _sync_state.update(running=False, ok=True, finished=_now_iso(), error=None)
    except Exception as exc:
        import traceback
        _sync_state.update(running=False, ok=False, finished=_now_iso(),
                           error=f"{type(exc).__name__}: {exc}",
                           traceback=traceback.format_exc()[-2000:])


def _now_iso() -> str:
    import datetime as _dt
    return _dt.datetime.now().isoformat(timespec="seconds")


@router.post("/api/sync")
def api_sync_start(what: str = "orders"):
    """Запустить-синк (по-кнопке). Возврат-мгновенный; прогресс —- в-/api/sync/status.
    Повторное-нажатие-во-время-работы —- 409 (фронт-просто-игнорирует)."""
    with _sync_lock:
        if _sync_state["running"]:
            raise HTTPException(status_code=409, detail="sync-уже-выполняется")
        _sync_state.update(running=True, started=_now_iso(), finished=None,
                           ok=None, error=None, result=None, traceback=None)
    _threading.Thread(target=_sync_worker, args=(what,), daemon=True).start()
    return {"started": True, "what": what, "state": _sync_state}


@router.get("/api/sync/status")
def api_sync_status():
    """Пульс-синка + свежесть-данных (для-подписи-«данные-на-…»)."""
    return {**_sync_state, "data_as_of": _data_freshness()}
