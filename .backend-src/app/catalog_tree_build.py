"""Сборщик персистентного снапшота дерева каталога (catalog_tree_stats) для /api/catalog/tree.

Фаза 3 рефакторинга (docs/REFACTOR_PLAN.md, раздел 3): цены меняются только при синке →
снапшот пересобирается рядом с branch_price_stats (хуки: daily_sync.sync_prices после
sync_prices и stage1_load.load_prices_v2 после загрузки цен); веб-роут (web_catalog.catalog_tree)
читает таблицу за миллисекунды, а при пустой/протухшей (built_at > 48ч) уходит в свой старый
тяжёлый путь-фолбэк. Паттерн 1:1 с _refresh_branch_price_stats (stage1_load.py):
TRUNCATE + INSERT одной транзакцией. Свёртка групп в семейства — общая детерминированная
_catalog_family из web_common (единственное место общего кода: импортируют и сборщик, и роут).
"""
from __future__ import annotations

import time

from web_common import _catalog_family

# Те же 2 тяжёлых запроса, что в фолбэке web_catalog._tree_heavy (дословно, плюс COALESCE
# для NOT NULL-колонок: kind/group_name в nomenclature_full допускают NULL):
_KINDS_SQL = """
    SELECT COALESCE(nf.kind, '—') AS kind, COUNT(*) AS n_items
    FROM nomenclature_full nf
    WHERE nf.is_deleted = false
    GROUP BY COALESCE(nf.kind, '—') ORDER BY n_items DESC
"""
_GROUPS_SQL = """
    SELECT COALESCE(nf.kind, '—') AS kind, COALESCE(nf.group_name, '—') AS group_name,
           COUNT(*) AS n_items,
           COUNT(DISTINCT p.nomenclature_id) FILTER (WHERE p.nomenclature_id IS NOT NULL) AS n_priced
    FROM nomenclature_full nf
    LEFT JOIN prices_history p ON p.nomenclature_id = nf.id_1c
    WHERE nf.is_deleted = false
    GROUP BY COALESCE(nf.kind, '—'), COALESCE(nf.group_name, '—')
"""


def rebuild_catalog_tree_stats(conn) -> int:
    """TRUNCATE+INSERT-в-catalog_tree_stats-(-счётчики-дерева-каталога-);-возвращает-число-строк-снапшота."""
    t0 = time.time()
    cur = conn.cursor()
    cur.execute(_KINDS_SQL)
    kind_totals = {kind: int(n or 0) for kind, n in cur.fetchall()}
    cur.execute(_GROUPS_SQL)
    rows = [
        (kind, _catalog_family(group_name), group_name, int(n_items or 0), int(n_priced or 0))
        for kind, group_name, n_items, n_priced in cur.fetchall()
    ]
    # TRUNCATE+INSERT одной транзакцией: веб-читатель всегда видит либо старый, либо новый снапшот:
    cur.execute("TRUNCATE catalog_tree_stats")
    cur.executemany(
        "INSERT INTO catalog_tree_stats (kind, family, group_name, n_items, n_priced, kind_total) VALUES (%s, %s, %s, %s, %s, %s)",
        [(k, f, g, n, p, kind_totals.get(k, 0)) for (k, f, g, n, p) in rows],
    )
    conn.commit()
    cur.close()
    # контроль: сумма n_items по группам вида = COUNT(*) вида (одинаковый WHERE — расхождений нет):
    sums: dict = {}
    for kind, _family, _group, n_items, _priced in rows:
        sums[kind] = sums.get(kind, 0) + n_items
    if any(sums.get(kind) != n for kind, n in kind_totals.items()):
        print("  catalog_tree_stats: WARNING — сумма n_items вида не сошлась с GROUP BY kind")
    print(f"  catalog_tree_stats: собран ({len(rows)} строк, {time.time() - t0:.1f}s)")
    return len(rows)


if __name__ == "__main__":
    import sys
    import db as _db
    conn = _db.connect()
    n = rebuild_catalog_tree_stats(conn)
    conn.close()
    print(f"каталог-дерево: {n} строк в catalog_tree_stats")
    sys.exit(0 if n > 0 else 1)
