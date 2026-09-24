"""Интеграционный smoke: backfill + (опц. live sync) + аналитические выборки.

Запуск:  PG_...=... python _itests.py [--live]
"""
import os, sys, logging
os.environ.update(PG_HOST="localhost", PG_PORT="55432", PG_DB="orders", PG_USER="orders", PG_PASSWORD="test")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

import db, sync as syncmod, config
import gl_api

key = [l.split("=", 1)[1].strip() for l in open(os.path.join(os.path.dirname(__file__), "..", ".env")) if l.startswith("API_KEY")][0]
config.API_KEY = key

conn = db.connect(); db.ensure_schema(conn)
print("=== schema applied ===")

if "--live" in sys.argv:
    counts = syncmod.sync(conn, key, with_details=True)
    print("SYNC:", counts)

counts = syncmod.backfill(conn, os.path.join(os.path.dirname(__file__), "..", "data"))
print("BACKFILL:", counts)

cur = conn.cursor()
for q, label in [
    ("SELECT count(*) FROM orders", "orders rows"),
    ("SELECT count(*) FROM orders WHERE detail_hash IS NOT NULL", "orders with details"),
    ("SELECT count(*) FROM order_items", "order_items"),
    ("SELECT count(*) FROM demand_items", "demand_items"),
    ("SELECT count(*) FROM order_status_history", "status_history"),
    ("SELECT count(*) FROM shipments", "shipments"),
    ("SELECT count(DISTINCT contractor_name) FROM orders", "distinct contractors"),
    # аналитические пробы:
    ("SELECT to_char(order_date, 'YYYY-MM') ym, count(*), round(sum(sum),2) FROM orders "
     "WHERE order_date >= '2025-01-01' GROUP BY 1 ORDER BY 1", "месячные итоги 2025+"),
    ("SELECT contractor_name, count(*), round(sum(sum),2) total FROM orders "
     "WHERE order_date >= '2025-06-01' GROUP BY 1 ORDER BY 3 DESC NULLS LAST LIMIT 5", "ТОП-5 контрагентов"),
]:
    print(f"--- {label}:")
    cur.execute(q)
    for row in cur.fetchall()[:15]:
        print("   ", row)
conn.commit()
conn.close()
print("=== INTEGRATION DONE ===")
