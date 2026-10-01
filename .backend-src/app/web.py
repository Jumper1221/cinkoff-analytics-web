"""Cinkoff Analytics API — read-only JSON API + статика SPA.

Запуск: python -u web.py  (0.0.0.0:8000, за nginx/traefik не нужен)

Фаза 7 (docs/REFACTOR_PLAN.md): это ТОЛЬКО сборщик — GZip, 2 мидлвари, маунты,
include_router ×6, /healthz и 2 SPA-страницы. Вся логика живёт в роутер-модулях
и web_common.
"""
from __future__ import annotations

import base64
import os
import sys

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

import web_common as _wcommon  # noqa: E402  (после sys.path-шапки)
from web_common import _cur, pool_stats  # noqa: E402
from fastapi.middleware.gzip import GZipMiddleware  # noqa: E402

app = FastAPI(title="Cinkoff Analytics", docs_url=None, redoc=None, openapi_url=None)
app.add_middleware(GZipMiddleware, minimum_size=1024)


@app.middleware("http")
async def cache_control(request, call_next):
    resp = await call_next(request)
    p = request.url.path
    if p.startswith("/static/vendor"):
        resp.headers["Cache-Control"] = "public, max-age=86400, immutable"   # 1 сутки, они не меняются
    elif p.startswith("/static"):
        resp.headers["Cache-Control"] = "public, max-age=300"                # 5 минут — свой код
    elif p.startswith("/api/branches") or p.startswith("/api/remnants/dates"):
        resp.headers["Cache-Control"] = "public, max-age=600"                # справочники 10 мин
    return resp


# ── Роутеры: 8+3+5+4+15+2 = 37 API-роутов, размазанных по фазам 2–6; каждый —
# чистое перемещение из web.py, пути/параметры дословно как были.
from web_catalog import router as _catalog_router
app.include_router(_catalog_router)

from web_people import router as _people_router
app.include_router(_people_router)

from web_stock import router as _stock_router
app.include_router(_stock_router)

from web_orders import router as _orders_router
app.include_router(_orders_router)

from web_dash import router as _dash_router
app.include_router(_dash_router)

from web_sync import router as _sync_router
app.include_router(_sync_router)


@app.middleware("http")
async def basic_auth_mw(request, call_next):
    pwd = os.getenv("WEB_PASSWORD", "")
    if pwd and not request.url.path.startswith(("/static",)):
        hdr = request.headers.get("authorization", "")
        ok = False
        if hdr.startswith("Basic "):
            try:
                u, p = base64.b64decode(hdr[6:]).decode().split(":", 1)
                ok = (u == "m" and p == pwd)
            except Exception:
                ok = False
        if not ok:
            # Лат-баг (фаза 7): PlainTextResponse использовался, но не был импортирован —
            # ветка 401 падала с 500. Импорт добавлен.
            return PlainTextResponse("auth", status_code=401, headers={"WWW-Authenticate": "Basic realm=cinkoff"})
    return await call_next(request)


@app.get("/healthz")
def healthz():
    try:
        with _cur() as cur:
            cur.execute("SELECT 1")
        return {"ok": True, "pool": _wcommon.pool_stats()}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)[:200]}, status_code=503)


# ── Статика SPA ──
app.mount("/static", StaticFiles(directory=os.path.join(BASE, "static")), name="static")


@app.get("/", response_class=HTMLResponse)
def spa():
    # R4: главная теперь = v2; легаси-SPA живёт на /legacy (и по-старому на /static/index.html)
    p = os.path.join(BASE, "static_v2", "index.html")
    with open(p, "rb") as f:
        return HTMLResponse(f.read().decode("utf-8"))


@app.get("/legacy", response_class=HTMLResponse, include_in_schema=False)
def legacy_spa():
    p = os.path.join(BASE, "static", "index.html")
    with open(p, "rb") as f:
        return HTMLResponse(f.read().decode("utf-8"))


# ── SPA v2 (Vue3+Vite+TS, каталог static_v2; легаси не тронут) ──
_V2 = os.path.join(BASE, "static_v2")
if os.path.isdir(_V2):

    class SPAStaticFiles(StaticFiles):
        """StaticFiles + SPA-fallback: несуществующий путь (без расширения) → index.html."""

        async def get_response(self, path: str, scope):
            try:
                resp = await super().get_response(path, scope)
            except StarletteHTTPException as e:
                if e.status_code == 404:
                    return FileResponse(os.path.join(self.directory, "index.html"))
                raise
            if resp.status_code == 404:
                return FileResponse(os.path.join(self.directory, "index.html"))
            return resp

    app.mount("/v2", SPAStaticFiles(directory=_V2, html=True), name="v2")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
