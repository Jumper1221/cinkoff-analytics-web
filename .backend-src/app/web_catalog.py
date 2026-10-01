"""Каталог-зона веб-слоя: 8 роутов каталога (search, prices, price_history, tree, branches,
items, surfaces) + товарная карточка /api/item/{nom_id}/card + _catalog_tree_cache.

Фаза 2 рефакторинга (docs/REFACTOR_PLAN.md): чистое перемещение из web.py, логика без изменений.
Регистрируется в web.py через include_router — пути/параметры дословно как были.
Фаза 3: /api/catalog/tree сначала читает персистентный снапшот catalog_tree_stats (сборщик —
catalog_tree_build.py, общая свёртка _catalog_family — в web_common); пусто/built_at > 48ч —
старый тяжёлый путь-фолбэк; +ETag (W/"built_at-rows") → 304 на If-None-Match.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Query, Request, Response

from web_common import _catalog_family, q, q1

router = APIRouter()


@router.get("/api/catalog/search")
def catalog_search(s: str = Query(min_length=2, max_length=100), limit: int = 25):
    like = f"%{s}%"
    return q("""
        SELECT n.id_1c, n.full_name, n.color, n.thickness, n.surface, n.weight, n.group_name,
               (SELECT COUNT(DISTINCT p.branch_id_1c) FROM prices_history p WHERE p.nomenclature_id = n.id_1c) AS branches
        FROM nomenclature_full n
        WHERE n.full_name ILIKE %s
        ORDER BY n.full_name
        LIMIT %s
    """, (like, min(limit, 100)))


@router.get("/api/catalog/prices/{nom_id}")
def catalog_prices(nom_id: str):
    return q("""
        SELECT p.branch_id_1c, b.name AS branch, p.price, p.discount_pct, p.discount_price, p.version_date
        FROM prices_history p
        LEFT JOIN branches b ON b.id_1c = p.branch_id_1c
        WHERE p.nomenclature_id = %s
        ORDER BY p.discount_price DESC NULLS LAST
    """, (nom_id,))


@router.get("/api/catalog/price_history/{nom_id}")
def catalog_price_history(nom_id: str, branch: str = ""):
    if branch:
        return q("""
            SELECT version_date, branch_id_1c, b.name AS branch, price, discount_price
            FROM prices_history p LEFT JOIN branches b ON b.id_1c = p.branch_id_1c
            WHERE nomenclature_id = %s AND p.branch_id_1c = %s
            ORDER BY version_date
        """, (nom_id, branch))
    return q("""
        SELECT DISTINCT ON (version_date::date, branch_id_1c)
               version_date, branch_id_1c, b.name AS branch, price, discount_price
        FROM prices_history p LEFT JOIN branches b ON b.id_1c = p.branch_id_1c
        WHERE nomenclature_id = %s
        ORDER BY version_date::date, branch_id_1c, version_date DESC
        LIMIT 500
    """, (nom_id,))


# --- Каталог (вкладка «Цены», переработка 29.09): дерево + точка отгрузки + текущие цены.

# --- Каталог (вкладка «Цены», переработка 29.09): дерево + точка отгрузки + текущие цены.

_catalog_tree_cache: dict = {"at": 0.0, "data": None, "etag": None}

# пусто/старше 48ч (2× интервал синка цен) → старый тяжёлый путь-фолбэк:
_TREE_SNAPSHOT_STALE = timedelta(hours=48)


def _tree_heavy() -> dict:
    """Старый-тяжёлый-путь-(-фолбэк-):-2-тяжёлых-SQL-по-13.5М-строк-цен-+-свёртка-в-Питоне-(~3-с-)."""
    kinds = q("""
        SELECT nf.kind, COUNT(*) AS n_items
        FROM nomenclature_full nf
        WHERE nf.is_deleted = false
        GROUP BY nf.kind ORDER BY n_items DESC
    """)
    groups = q("""
        SELECT nf.kind, nf.group_name, COUNT(*) AS n_items,
               COUNT(DISTINCT p.nomenclature_id) FILTER (WHERE p.nomenclature_id IS NOT NULL) AS n_priced
        FROM nomenclature_full nf
        LEFT JOIN prices_history p ON p.nomenclature_id = nf.id_1c
        WHERE nf.is_deleted = false
        GROUP BY nf.kind, nf.group_name
    """)
    by_kind: dict = {}
    for g in groups:
        by_kind.setdefault(g["kind"], []).append(g)
    tree = []
    for k in kinds:
        gs = by_kind.get(k["kind"], [])
        # свёртка групп в семейства по префиксу имени (заводская иерархия):
        fams: dict = {}
        for g in gs:
            fam_groups = fams.setdefault(_catalog_family(g["group_name"]), [])
            fam_groups.append(g)
        fam_list = [
            {
                "family": f,
                "n_items": sum(int(g["n_items"] or 0) for g in fs2),
                "n_priced": sum(int(g["n_priced"] or 0) for g in fs2),
                "groups": sorted(fs2, key=lambda g: -int(g["n_items"] or 0)),
            }
            for f, fs2 in fams.items()
        ]
        fam_list.sort(key=lambda f: -f["n_items"])
        tree.append({
            "kind": k["kind"], "n_items": k["n_items"],
            "n_families": len(fam_list),
            "families": fam_list,
        })
    return {"kinds": tree}


def _tree_from_snapshot() -> "tuple[dict, str] | None":
    """Снапшот-путь: чтение catalog_tree_stats (~2-3 тыс. строк, миллисекунды) → та же JSON-структура.

    Сборка дословно как в фолбэке (свёртка семейств — та же _catalog_family из web_common,
    те же сортировки и порядок ключей), только группы-строки читаются из снапшота.
    Пустая таблица или built_at старше _TREE_SNAPSHOT_STALE → None (роут уходит в фолбэк).
    """
    rows = q("""
        SELECT kind, family, group_name, n_items, n_priced, kind_total, built_at
        FROM catalog_tree_stats
        ORDER BY kind, family, group_name
    """)
    if not rows:
        return None
    built_at = max(r["built_at"] for r in rows)
    if datetime.now(timezone.utc) - built_at > _TREE_SNAPSHOT_STALE:
        return None
    by_kind: dict = {}
    for g in rows:
        by_kind.setdefault(g["kind"], []).append(g)
    tree = []
    for kind, gs in by_kind.items():
        # свёртка групп в семейства по префиксу имени (заводская иерархия):
        fams: dict = {}
        for g in gs:
            fam_groups = fams.setdefault(_catalog_family(g["group_name"]), [])
            fam_groups.append(g)
        fam_list = [
            {
                "family": f,
                "n_items": sum(int(g["n_items"] or 0) for g in fs2),
                "n_priced": sum(int(g["n_priced"] or 0) for g in fs2),
                "groups": [
                    # ключи/порядок — ровно как в фолбэке (SELECT-порядок колонок):
                    {"kind": g["kind"], "group_name": g["group_name"],
                     "n_items": int(g["n_items"] or 0), "n_priced": int(g["n_priced"] or 0)}
                    for g in sorted(fs2, key=lambda g: -int(g["n_items"] or 0))
                ],
            }
            for f, fs2 in fams.items()
        ]
        fam_list.sort(key=lambda f: -f["n_items"])
        # n_items вида — kind_total из снапшота (COUNT(*) номенклатуры вида, считает сборщик;
        # n_items групп — строки после 1:N-LEFT-JOIN цен, это другая величина, как в фолбэке):
        kind_total = next((int(g["kind_total"] or 0) for g in gs if g.get("kind_total") is not None), 0)
        tree.append({
            "kind": kind, "n_items": kind_total,
            "n_families": len(fam_list),
            "families": fam_list,
        })
    tree.sort(key=lambda k: -k["n_items"])
    # ETag по версии снапшота (built_at+rows), не от payload — дёшево и стабильно:
    etag = f'W/"{int(built_at.timestamp())}-{len(rows)}"'
    return {"kinds": tree}, etag


@router.get("/api/catalog/tree")
def catalog_tree(request: Request, response: Response):
    """Дерево каталога: вид → семейство → группы (с числом товаров/позиций с ценами).

    Фаза 3: сперва снапшот catalog_tree_stats (миллисекунды, собирается при синке цен —
    catalog_tree_build.rebuild_catalog_tree_stats); пусто/протух (built_at > 48ч) → старый
    тяжёлый путь (гарантия «никогда не хуже текущего»). Кэш процесса 30 мин сохранён —
    он лишь снимает и эти миллисекунды; ETag → 304 без тела на If-None-Match.
    """
    import time as _time
    now = _time.time()
    if now - _catalog_tree_cache["at"] > 1800 or not _catalog_tree_cache["data"]:
        snap = _tree_from_snapshot()
        if snap is None:
            data, etag = _tree_heavy(), None
        else:
            data, etag = snap
        _catalog_tree_cache["at"] = now
        _catalog_tree_cache["data"] = data
        _catalog_tree_cache["etag"] = etag
    etag = _catalog_tree_cache.get("etag")
    if etag:
        response.headers["ETag"] = etag
        if request.headers.get("if-none-match") == etag:
            return Response(status_code=304, headers={"ETag": etag})
    return _catalog_tree_cache["data"]


@router.get("/api/catalog/branches")
def catalog_branches():
    """Точки-отгрузки, по-которым-есть-цены.

    Читает-сводку-branch_price_stats-(-пересобирается-после-каждой-загрузки-цен-),
    чтобы-не-сканировать-13.5M-строк-prices_history-на-каждый-запрос-(-было---19-20-сек-).
    Если-сводка-пуста-(-первый-запуск-до-первого-синка-)-подсчёт-на-лету-и-кэш-на-5-мин.
    """
    rows = q("SELECT s.branch_id_1c AS id_1c, b.name, s.n_items AS n_items"
             " FROM branch_price_stats s JOIN branches b ON b.id_1c = s.branch_id_1c"
             " ORDER BY b.name")
    if rows:
        return rows
    # фолбэк:---старый-тяжёлый-подсчёт (сводка-ещё-не-собрана)
    rows = q("""
        SELECT b.id_1c, b.name, COUNT(DISTINCT p.nomenclature_id) AS n_items
        FROM prices_history p JOIN branches b ON b.id_1c = p.branch_id_1c
        GROUP BY b.id_1c, b.name ORDER BY b.name
    """)
    return rows


@router.get("/api/catalog/items")
def catalog_items(branch: str, group: str = "", kind: str = "", search: str = "",
                  surface: str = "", limit: int = 50, offset: int = 0):
    """Товары выбранной точки: текущая цена (последняя версия), поиск, пагинация.

    group = точная группа 1С; без group, но с kind = семейство (по префиксу группы);
    surface = покрытие внутри группы (с нормализацией вариантов: «Полиэстер матовый
    двухсторонний» → «Полиэстер» — это одно покрытие с разными свойствами листа).
    limit/offset — стандартные имена, так约定的 контрактом (выбор Михаила).
    """
    branch = branch.strip()
    if not branch:
        return {"total": 0, "items": []}
    lim = max(1, min(200, limit))
    off = max(0, offset)
    # DISTINCT ON: последняя версия цены товара в этой точке. Цены двух соглашений
    # совпадают (проверено 29.09: 206 607 пар, различий 0) — единственная версия на товар.
    wh = ["nf.is_deleted = false"]
    search_param = ""
    group_param = ""
    if group:
        wh.append("nf.group_name = %s")
        group_param = group.strip()
    if search:
        wh.append("nf.full_name ILIKE %s")
        search_param = f"%{search.strip()}%"
    where = " AND ".join(wh)
    # --- Покрытие (surface) внутри группы: база-без-«двухсторонний/слим/матовый/ТХ/ТР/СТ».
    surf_f = ""
    if group and surface.strip():
        s = " ".join(surface.strip().split())
        # базовое-имя-покрытия = отсечь-хвостовые-модификаторы-(-до-первого-ключевого-слова-):
        base = s
        for mod in [" двухсторонний", " слим", " матовый", " ТХ", " ТР", " СТ", " TwinColor"]:
            if base.endswith(mod):
                base = base[: -len(mod)]
        # соответствие-в-SQL:---точное-ИЛИ-точное-«база+свойство»-(-«Полиэстер»+«Полиэстер двухсторонний»...-)
        surf_f = "AND (btrim(nf.surface) = %s OR btrim(nf.surface) = %s OR btrim(nf.surface) = %s)"
        surf_params = [base, f"{base} слим", f"{base} матовый"]
        # «двухсторонний»-в-базе-(-Полиэстер двухсторонний-)-и-«...матовый двухсторонний»:
        if s.endswith("двухсторонний"):
            surf_f = "AND (btrim(nf.surface) = %s OR btrim(nf.surface) = %s OR btrim(nf.surface) = %s OR btrim(nf.surface) = %s)"
            base2 = base
            args_b = [base2, f"{base2} матовый", f"{base2} слим", f"{base2} матовый двухсторонний"]
            surf_params = args_b
        if base == "Полиэстер":
            surf_f = "AND (btrim(nf.surface) = 'Полиэстер' OR btrim(nf.surface) = 'Полиэстер слим' OR btrim(nf.surface) = 'Полиэстер матовый' OR btrim(nf.surface) = 'Полиэстер двухсторонний' OR btrim(nf.surface) = 'Полиэстер матовый двухсторонний' OR btrim(nf.surface) = 'Полиэстер матовый')"
            surf_params = []
        if base == "Сатин":
            surf_f = "AND (btrim(nf.surface) = 'Сатин' OR btrim(nf.surface) = 'Сатин матовый' OR btrim(nf.surface) = 'Сатин матовый ТХ' OR btrim(nf.surface) = 'Сатин матовый ТХ-35')"
            surf_params = []
        if base == "Drap":
            surf_f = "AND (btrim(nf.surface) = 'Drap' OR btrim(nf.surface) LIKE 'Drap %')"
            surf_params = []
        if base == "Принт":
            surf_f = "AND (btrim(nf.surface) = 'Принт Премиум' OR btrim(nf.surface) = 'Принт Элит' OR btrim(nf.surface) = 'Принт Премиум двухсторонний' OR btrim(nf.surface) = 'Принт Элит двухсторонний')"
            surf_params = []
    fam_f = ""
    final_args = [branch]
    if not group:
        fam = (kind or "").strip()
        if fam == "Виниловый водосток":
            fam_f = "AND (nf.group_name ILIKE 'Виниловый водосток%' OR nf.group_name = 'Водосток')"
        elif fam:
            fam_f = "AND nf.group_name ILIKE %s"
            final_args.append(fam + "%")
    final_args += ([group_param] if group_param else [])
    if surf_f:
        if surf_params:
            final_args += surf_params
        else:
            pass  # литеральные-сравнения-без-параметров
    final_args += ([search_param] if search_param else [])
    total = q1(f"""
        SELECT COUNT(*) AS n FROM (
          SELECT DISTINCT p.nomenclature_id
          FROM prices_history p
          JOIN nomenclature_full nf ON nf.id_1c = p.nomenclature_id
          WHERE p.branch_id_1c = %s AND 1=1 {fam_f} AND {where} {surf_f}
        ) t
    """, tuple(final_args))["n"]
    rows = q(f"""
        SELECT nf.id_1c, nf.code_1c, nf.full_name, nf.group_name, nf.color, nf.thickness, nf.surface,
               l.price::float8 AS price, l.discount_pct::float8 AS discount_pct,
               l.discount_price::float8 AS discount_price, l.version_date
        FROM (SELECT DISTINCT ON (p2.nomenclature_id) p2.nomenclature_id, p2.price, p2.discount_pct,
                     p2.discount_price, p2.version_date
              FROM prices_history p2 WHERE p2.branch_id_1c = %s
              ORDER BY p2.nomenclature_id, p2.version_date DESC) l
        JOIN nomenclature_full nf ON nf.id_1c = l.nomenclature_id
        WHERE 1=1 {fam_f} AND {where} {surf_f}
        ORDER BY nf.full_name LIMIT {lim} OFFSET {off}
    """, tuple([branch] + final_args[1:]))  # первый-branch-уже-в-строке-DISTINCT-ON
    return {"total": int(total), "items": rows}


@router.get("/api/catalog/surfaces")
def catalog_surfaces(branch: str, group: str):
    """Разбивка-покрытий (surface) внутри группы 1С — для-4-го-уровня-дерева.

    Возвращает-«базовые-покрытия» (без-хвостов-«матовый/двухсторонний/слим/ТХ...»)
    со-счётчиком-позиций:---«Полиэстер двухсторонний»-и-«Полиэстер матовый»-→-«Полиэстер».
    """
    branch = branch.strip()
    g = group.strip()
    if not branch or not g:
        return {"groups": []}
    rows = q("""
        SELECT COALESCE(NULLIF(btrim(nf.surface), ''), '—') AS surf, COUNT(*) AS n
        FROM nomenclature_full nf
        WHERE nf.group_name = %s AND nf.is_deleted = false
        GROUP BY 1 ORDER BY 2 DESC
    """, (g,))
    # нормализация:---«Полиэстер матовый»→«Полиэстер»,-«Drap ТХ»→«Drap»-и-т.п.
    def _base(s: str) -> str:
        if s == "—": return s
        for suf in [" двухсторонний", " слим", " матовый", " ТХ", " ТР", " СТ", " TwinColor", " матовый двухсторонний"]:
            if s.endswith(suf):
                return _base(s[: -len(suf)])
        # «Принт Премиум»-и-«Принт Элит»-→-«Принт»
        if s.startswith("Принт "): return "Принт"
        if s.startswith("GreenCoat Pural"): return "GreenCoat Pural"
        if s.startswith("Полидэкстер"): return "Полидэкстер"
        if s.startswith("PurPro"): return "PurPro"
        if s.startswith("PurLite"): return "PurLite"
        if s.startswith("Rooftop"): return "Rooftop"
        if s.startswith("Velur"): return "Velur"
        if s.startswith("Атлас"): return "Атлас"
        if s.startswith("Цинк"): return "Цинк"
        return s
    agg: dict = {}
    for r in rows:
        b = _base(r["surf"])
        agg[b] = agg.get(b, 0) + int(r["n"])
    # порядок---по-количеству
    items = sorted(agg.items(), key=lambda kv: -kv[1])
    return {"group": g, "total": sum(agg.values()),
            "surfaces": [{"surface": k, "n": v} for k, v in items if k != "—"]}


@router.get("/api/item/{nom_id}/card")
def item_card(nom_id: str):
    """Карточка товара: продажи (всего/12мес/последний раз), динамика цены (месяц-срезы), остатки по складам, покупают вместе."""
    sold_all = q1("""
        SELECT COALESCE(SUM(i.quantity),0)::float8 AS units, COALESCE(SUM(i.total),0)::float8 AS revenue,
               COUNT(DISTINCT i.orders_id)::int AS orders_cnt, MAX(o.order_date) AS last_order
        FROM order_items i JOIN orders o ON o.id = i.orders_id
        WHERE i.id_1c = %s AND i.kind = 'nomenclature'
    """, (nom_id,))
    sold12 = q1("""
        SELECT COALESCE(SUM(i.quantity),0)::float8 AS units, COALESCE(SUM(i.total),0)::float8 AS revenue
        FROM order_items i JOIN orders o ON o.id = i.orders_id
        WHERE i.id_1c = %s AND i.kind = 'nomenclature' AND o.order_date >= now() - interval '12 months'
    """, (nom_id,))
    # динамика цены: 1-й день месяца → min(discount_price) по 22789-агр-ветке (id 4d30…)
    price_hist = q("""
        SELECT to_char(version_date, 'YYYY-MM-01') AS month, MIN(discount_price)::float8 AS min_price,
               MAX(price)::float8 AS max_list
        FROM prices_history WHERE nomenclature_id = %s
        GROUP BY 1 ORDER BY 1
    """, (nom_id,))
    remnants = q("""
        SELECT COALESCE(b.name, r.storage_id) AS branch, r.qty, r.delivery_date, r.snapshot_date
        FROM remnants_snapshots r LEFT JOIN branches b ON b.id_1c = r.storage_id
        WHERE r.nomenclature_id = %s AND r.kind = 'metall' AND (r.qty > 0 OR r.delivery_date IS NOT NULL)
          AND r.snapshot_date = (SELECT MAX(s2.snapshot_date) FROM remnants_snapshots s2 WHERE s2.kind = 'metall')
        ORDER BY r.qty DESC
    """, (nom_id,))
    # покупают вместе: другие позиции, встречающиеся в тех же заказах
    together = q("""
        SELECT i2.name, COUNT(DISTINCT i2.orders_id)::int AS cnt, SUM(i2.quantity)::float8 AS units
        FROM order_items i2
        WHERE i2.orders_id IN (SELECT orders_id FROM order_items WHERE id_1c = %s)
          AND i2.id_1c <> %s AND i2.kind = 'nomenclature'
        GROUP BY 1 ORDER BY 2 DESC LIMIT 8
    """, (nom_id, nom_id))
    info = q1("SELECT id_1c, full_name, color, thickness, surface, weight, group_name, kind FROM nomenclature_full WHERE id_1c = %s", (nom_id,))
    if not info:
        info = q1("SELECT id_1c, name AS full_name, group_name FROM nomenclature WHERE id_1c = %s", (nom_id,))
    return {"info": info, "sold_all": sold_all, "sold12": sold12,
            "price_history": price_hist, "remnants": remnants, "together": together}
