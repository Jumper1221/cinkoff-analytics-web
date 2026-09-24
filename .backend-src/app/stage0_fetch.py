"""Этап 0: разовая выгрузка ВСЕГО, что отдаёт API -> data/snapshots/initial-*/ + журнал.

Правило (решение Михаила): сначала сырой JSON на диск, потом (отдельно) БД.
Запуск:  python -u stage0_fetch.py            # всё по порядку, резюмируемо
         python -u stage0_fetch.py details    # только детали (продолжение)
"""
import json, os, sys, time, gzip, logging, concurrent.futures as cf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import requests

KEY = [l.split("=",1)[1].strip() for l in open(os.path.join(os.path.dirname(__file__), "..", ".env")) if l.startswith("API_KEY")][0]
API = "https://client.grandline.ru/api/public"
GAPI = "https://client.grandline.ru/go/api/public"
S = requests.Session(); S.headers["User-Agent"] = "cinkoff-stage0/1.0"

STAMP = "2026-09-23"
ROOT = os.path.join(os.path.dirname(__file__), "..", "data", "snapshots", f"initial-{STAMP}")
os.makedirs(ROOT, exist_ok=True)
LOG = open(os.path.join(ROOT, "progress.log"), "a", buffering=1)
def log(msg): LOG.write(f"{time.strftime('%H:%M:%S')} {msg}\n"); print(f"  {time.strftime('%H:%M:%S')} {msg}")

def sess():
    s = requests.Session(); s.headers["User-Agent"] = "cinkoff-stage0/1.0"; return s
SS = sess()

def fetch(url, **params):
    """GET c ретраями (429/timeout/conn), -> json|None."""
    params["api_key"] = KEY
    for att in range(6):
        try:
            r = SS.get(url, params=params, timeout=(15, 120))
        except (requests.ConnectTimeout, requests.ReadTimeout, requests.ConnectionError):
            time.sleep(4); continue
        if r.status_code == 429:
            time.sleep(2.5); continue
        if r.status_code == 200:
            try: return r.json()
            except Exception: time.sleep(2); continue
        time.sleep(2)
    return None

def save(name, data, compress=True):
    import gzip
    p = os.path.join(ROOT, name + (".json.gz" if compress else ".json"))
    if compress:
        blob = json.dumps(data, ensure_ascii=False, separators=(",",":")).encode()
        with gzip.open(p + ".tmp", "wb") as f: f.write(blob)
    else:
        with open(p + ".tmp", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    os.replace(p + ".tmp", p)
    mb = os.path.getsize(p) / 1e6
    log(f"saved {name} ({mb:.2f} MB)")
    return p

def done(name):
    for cand in (os.path.join(ROOT, name),
                 os.path.join(ROOT, name + ".json.gz"),
                 os.path.join(ROOT, name + ".json"),
                 os.path.join(ROOT, (name[:-3] if name.endswith(".gz") else name) + ".json.gz")):
        if os.path.exists(cand):
            return True
    return False

# ── Блок 1: заказы-шапки (вся история) ──────────────────────────────
def step_details(max_items=None):
    """Детали по всем order_id, 3 параллельных воркера, пачки по 500 -> gzip-файл."""
    import gzip, math
    src_path = os.path.join(ROOT, "orders_all.json.gz")
    if not os.path.exists(src_path):
        log("нет orders_all — детали пропускаю"); return
    with gzip.open(src_path, "rt", encoding="utf-8") as f:
        rows = json.load(f)
    ids = [r["order_id"] for r in rows if r.get("order_id")]
    out = os.path.join(ROOT, "details")
    os.makedirs(out, exist_ok=True)
    part = 500
    nparts = math.ceil(len(ids)/part)
    def done_parts():
        return {int(f.split("_")[1].split(".")[0]) for f in os.listdir(out) if f.endswith(".json.gz")}
    log(f"details: {len(ids)} id, {nparts} пачек, готово: {len(done_parts())}")
    import concurrent.futures as _cf
    def grab(oid):
        d = fetch(f"{API}/orders/{oid}/")
        if isinstance(d, dict):
            d["_order_id"] = oid
        return oid, d
    for pi in range(nparts):
        fn = f"details_{pi:03d}.json.gz"
        if pi in done_parts():
            continue
        if max_items and pi >= max_items:
            break
        t0 = time.time()
        chunk = {}
        with _cf.ThreadPoolExecutor(max_workers=3) as ex:
            for oid, d in ex.map(grab, ids[pi*part:(pi+1)*part]):
                if d is not None:
                    chunk[oid] = d
        blob = json.dumps(chunk, ensure_ascii=False, separators=(",",":")).encode()
        import gzip as g2
        with g2.open(os.path.join(out, fn) + ".tmp", "wb") as f:
            f.write(blob)
        os.replace(os.path.join(out, fn) + ".tmp", os.path.join(out, fn))
        rate = len(chunk)/(time.time()-t0)
        log(f"details: пачка {pi+1}/{nparts}: {len(chunk)} записей ({rate:.1f} заказа/с, всего готово {len(done_parts())}/{nparts})")

def step_paged(path, fname, base=API, key="offset", step=20000, max_pages=40):
    import gzip
    if os.path.exists(os.path.join(ROOT, fname + ".json.gz")):
        return
    allrows, offset = [], 0
    while True:
        url = f"{base}/{path}"
        d = fetch(url, offset=offset)
        if not isinstance(d, list) or not d:
            break
        save_part = d
        # накапливаем в файл (потоково через многие-страничный gzip)
        allrows = locals().setdefault("_acc", [])
        allrows.extend(d)
        if len(d) < step:
            break
        offset += step
        if len(allrows) > (max_pages or 10**9) * step:
            break
        time.sleep(0.4)
    blob = allrows
    import gzip as gz
    p = os.path.join(ROOT, f"{path.replace('/','_').strip('_')}.json.gz")
    with gz.open(p + ".tmp", "wb") as f:
        f.write(json.dumps(blob, ensure_ascii=False, separators=(",",":")).encode())
    os.replace(p + ".tmp", p)
    log(f"saved {path} -> {len(blob)} записей ({os.path.getsize(p)/1e6:.1f} MB)")

def step_small():
    for name, path in [("branches", "branches/"), ("agreements", "agreements/"),
                       ("nomenclature_groups", "nomenclature_groups/")]:
        if done(f"{name}.json"): continue
        d = fetch(f"{API}/{name}/")
        if isinstance(d, list):
            with open(os.path.join(ROOT, f"{name}.json"), "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False)
            log(f"saved {name} ({len(d)})")
        time.sleep(0.4)
    if not done("vehicle_brands.json"):
        d = fetch(f"{GAPI}/vehicle-brands/")
        if isinstance(d, list):
            with open(os.path.join(ROOT, "vehicle_brands.json"), "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False)
            log(f"saved vehicle_brands ({len(d)})")

# ── Главная ──

GAPI = "https://client.grandline.ru/go/api/public"

def step_orders():
    """Полная история заказов (шапки) с 2019: /go/api/public/orders/active/ без дат."""
    if os.path.exists(os.path.join(ROOT, "orders_all.json.gz")):
        log("orders_all: уже есть, пропускаю"); return
    t = time.time()
    rows = fetch(f"{GAPI}/orders/active/")
    assert isinstance(rows, list) and len(rows) > 1000, f"неList: {str(rows)[:100]}"
    save("orders_all.json.gz", rows)
    log(f"orders: {len(rows)} записей, {time.time()-t:.1f}s")

def step_catalog():
    """nomenclatures: 12 стр по 20k через offset."""
    import gzip as gz
    out = os.path.join(ROOT, "nomenclatures_all.json.gz")
    if os.path.exists(out):
        log("nomenclatures: уже есть"); return
    t = time.time()
    allrows, offset, pages = [], 0, 0
    while True:
        d = fetch(f"{API}/nomenclatures/", offset=offset)
        if not isinstance(d, list) or not d: break
        allrows.extend(d)
        print(f"    +{len(d)} (итого {len(allrows)})", flush=True)
        if len(d) < 20000: break
        offset += 20000
        time.sleep(0.5)
    with gz.open(out + ".tmp", "wb") as f:
        f.write(json.dumps(allrows, ensure_ascii=False, separators=(",",":")).encode())
    os.replace(out + ".tmp", out)
    log(f"nomenclatures: {len(allrows)} записей, {time.time()-t:.0f}s ({os.path.getsize(out)/1e6:.1f} MB)")

def step_remnants():
    import gzip, math
    out_dir = os.path.join(ROOT, "remnants")
    os.makedirs(out_dir, exist_ok=True)
    if os.listdir(out_dir):
        log("remnants: уже есть, пропускаю"); return
    t = time.time()
    n, offset, pi = 0, 0, 0
    while True:
        d = fetch(f"{API}/remnants/", offset=offset)
        if not isinstance(d, list) or not d: break
        blob = json.dumps(d, ensure_ascii=False, separators=(",",":")).encode()
        fn = os.path.join(out_dir, f"remnants_{pi:03d}.json.gz")
        with gzip.open(fn + ".tmp", "wb") as f: f.write(blob)
        os.replace(fn + ".tmp", fn)
        log(f"remnants: стр.{pi} +{len(d)} (итого {n+len(d)})")
        n += len(d); pi += 1; offset += 20000
        if len(d) < 20000: break
        time.sleep(0.5)
    log(f"remnants: {n} записей, {math.ceil(n/20000)} пачек, {time.time()-t:.0f}s")

def step_prices():
    """prices по (branch x agreement): сначала узнаём валидные пары.
    Внутри: /api/public/prices/?branch_id_1c&agreement_id_1c&offset (20000/стр)."""
    import gzip
    branches = json.load(open(os.path.join(ROOT, "branches.json"))) if os.path.exists(os.path.join(ROOT, "branches.json")) else fetch(f"{API}/branches/")
    agreements = fetch(f"{API}/agreements/")
    out_dir = os.path.join(ROOT, "prices")
    os.makedirs(out_dir, exist_ok=True)
    # обе парыbranch×agreement можно пробить маленьким запросом (limit=1) — 400-ответ = невалидная
    combos = []
    for b in branches or []:
        for a in (agreements if isinstance(agreements := agreements, list) else agreements_for(a)) if False else agreements:
            time.sleep(0.3)
            probe = fetch(f"{API}/prices/", branch_id_1c=b["id_1c"], agreement_id_1c=a["id_1c"])
            if isinstance(probe, list) and probe:
                combos.append((b, a))
    log(f"prices: валидных пар (branch, agreement): {len(combos)}")
    for (b, a) in combos:
        bname = b.get("name", b["id_1c"][:8]).replace("/", "-").replace(" ", "_")
        aname = a.get("name", a["id_1c"][:8]).split(";")[0].strip().replace("/", "-").replace(" ", "_")
        out = os.path.join(out_dir, f"prices__{bname}__{aname}")
        os.makedirs(out, exist_ok=True)
        if os.listdir(out):
            continue
        t0, offset, pi, all_count = time.time(), 0, 0, 0
        while True:
            d = fetch(f"{API}/prices/", branch_id_1c=b["id_1c"], agreement_id_1c=a["id_1c"], offset=offset)
            if not isinstance(d, list) or not d: break
            blob = json.dumps(d, ensure_ascii=False, separators=(",",":")).encode()
            fn = os.path.join(out, f"prices_{bname[:20]}__{aname[:20]}_{pi:03d}.json.gz")
            with gzip.open(fn + ".tmp", "wb") as f: f.write(blob)
            os.replace(fn + ".tmp", fn)
            all_count += len(d); pi += 1; offset += 20000
            if len(d) < 20000: break
            time.sleep(0.6)
        log(f"prices {bname} x {aname}: {all_count} цен, {pi} пачек, {time.time()-t0:.0f}s")

def step_misc():
    """certificates + pim-attributes (200/стр) — быстрые."""
    import gzip
    for name, path in [("certificates", "catalog/certificates/"), ("pim_attributes", "catalog/pim-attributes/")]:
        out = os.path.join(ROOT, f"{name}.json.gz")
        if os.path.exists(out): continue
        t = time.time()
        allrows, offset = [], 0
        while True:
            d = fetch(f"{API}/{path}", limit=200, offset=offset)
            if not isinstance(d, list) or not d: break
            allrows.extend(d)
            if len(d) < 200: break
            offset += 200
            time.sleep(0.3)
        if allrows:
            with gzip.open(out + ".tmp", "wb") as f:
                f.write(json.dumps(allrows, ensure_ascii=False, separators=(",",":")).encode())
            os.replace(out + ".tmp", out)
            log(f"saved {name}: {len(allrows)} ({os.path.getsize(out)/1e6:.2f} MB, {time.time()-t:.0f}s)")
        time.sleep(0.4)

# ссылки на файлы: только по встреченной в заказах номенклатуре (не по всем 231k)
def step_files():
    import gzip
    out = os.path.join(ROOT, "nomenclature_files.json.gz")
    if os.path.exists(out): return
    # составить множество id из order-деталей (нужен orders+details) — иначе пропустить
    ids = set()
    ddir = os.path.join(ROOT, "details")
    if not os.path.isdir(out_dir := os.path.join(ROOT, "details")):
        log("files: деталей ещё нет, скип"); return
    for fn in os.listdir(out_dir):
        if not fn.endswith(".json.gz"): continue
        with gzip.open(os.path.join(out_dir, fn), "rb") as f:
            for oid, d in json.load(f).items():
                for it in (d.get("order_nomenclatures") or []):
                    if it.get("id_1c"): ids.add(it["id_1c"])
    log(f"files: уникальной номенклатуры в заказах: {len(ids)}")
    results = []
    for i, nid in enumerate(sorted(ids)):
        d = fetch(f"{API}/catalog/get-nomenclature-files/{nid}/")
        if isinstance(d, list):
            for rec in d:
                rec["_nomenclature_id"] = nid
                rows = rec
                allrows = locals().get("allrows", [])
                allrows.append(rec)
        if (i+1) % 100 == 0:
            log(f"files: {i+1} позиций осмотрено")
        time.sleep(0.2)
    with gzip.open(out + ".tmp", "wb") as f:
        f.write(json.dumps(allrows, ensure_ascii=False, separators=(",",":")).encode())
    os.replace(out + ".tmp", out)
    log(f"files: {len(allrows)} ссылок сохранено")

if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    t0 = time.time()
    if what in ("all", "orders"):
        step_small()      # branches/agreements/vehicle_brands — нужны для всех остальных шагов
        step_orders()
    if what in ("all", "details"):
        step_details()
    if what in ("all", "catalog"):
        step_catalog()
    if what in ("all", "remnants"):
        step_remnants()
    if what in ("all", "prices"):
        step_prices()
    if what in ("all", "misc"):
        step_misc()
    log(f"STAGE0 '{what}' done in {time.time()-t0:.0f}s")
