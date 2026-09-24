-- Cinkoff Orders Analytics: схема Postgres 15+ (NULLS NOT DISTINCT).
-- Идемпотентна: все объекты IF NOT EXISTS. Применяется при каждом старте.

-- ── Словари (заполняются только из деталей; имена всегда денормализованы в orders) ──
CREATE TABLE IF NOT EXISTS contractors (
    id_1c      TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS branches (
    id_1c       TEXT PRIMARY KEY,
    code_1c     TEXT,
    name        TEXT NOT NULL,
    address     TEXT,
    latitude    DOUBLE PRECISION,
    longitude   DOUBLE PRECISION,
    description TEXT,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS agreements (
    id_1c             TEXT PRIMARY KEY,
    code_1c           TEXT,
    name              TEXT,
    debt_check_method TEXT,
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS nomenclature (
    id_1c      TEXT PRIMARY KEY,
    code_1c    TEXT,
    name       TEXT,
    group_name TEXT,
    unit       TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── Заказы ──
-- Источник строк: API-список, API-детали, исторические дампы (source).
-- COALESCE-обновление: list-апдейты не стирают то, что принесли детали.
CREATE TABLE IF NOT EXISTS orders (
    id                        BIGSERIAL PRIMARY KEY,
    order_id                  BIGINT,            -- int-номер заказа поставщика (может отсутствовать)
    id_1c                     TEXT,              -- гуид в 1С (может отсутствовать)
    number                    TEXT,              -- "УО-02129157"
    order_date                TIMESTAMPTZ,
    ordered_date              TIMESTAMPTZ,       -- когда создан (ordered_date)
    order_status              TEXT,
    payment_status            TEXT,
    sale_status               TEXT,
    client_confirm_state      TEXT,
    contractor_id_1c          TEXT,
    contractor_name           TEXT,
    branch_id_1c              TEXT,
    branch_name               TEXT,
    agreement_id_1c           TEXT,
    agreement_name            TEXT,
    additional_agreement_name TEXT,
    debt_check_method         TEXT,
    supplier_name             TEXT,
    subcontractor_name        TEXT,
    sum                       NUMERIC(14,2),     -- сумма заказа
    weight                    INTEGER,           -- кг
    planned_shipment_date     TIMESTAMPTZ,
    planned_delivery_date     TIMESTAMPTZ,
    shipment_date             TIMESTAMPTZ,       -- order_shipment_date
    comment                   TEXT,
    demand_id                 BIGINT,
    demand_status             TEXT,
    demand_date               TIMESTAMPTZ,
    demand_create_date        TIMESTAMPTZ,
    demand_responsible        TEXT,
    demand_sum                NUMERIC(14,2),     -- сумма реализованного (из деталей)
    demand_weight             INTEGER,
    demand_delivery_cost      NUMERIC(12,2),
    demand_delivery_type      TEXT,
    demand_is_delivery        BOOLEAN,
    demand_address            TEXT,
    demand_lat                NUMERIC(9,6),
    demand_lon                NUMERIC(9,6),
    is_ready_for_shipment     BOOLEAN,
    is_transport_docs         BOOLEAN,
    is_allow_online_payment   BOOLEAN,
    has_completed_shipment    BOOLEAN,
    detail_hash               TEXT,              -- SHA256 деталей; NULL => деталей ещё нет
    detail_fetched_at         TIMESTAMPTZ,       -- когда детали реально грузились (для TTL)
    list_sig                  TEXT,              -- сигнатура волатильных полей списка
    source                    TEXT NOT NULL DEFAULT 'api',   -- api | backfill:<файл>
    raw_detail                JSONB,             -- последняя сырая деталь (если была)
    raw_list                  JSONB,             -- последняя сырая запись списка
    created_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
    fetched_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE NULLS NOT DISTINCT (order_id, id_1c)
);

CREATE INDEX IF NOT EXISTS idx_orders_order_date  ON orders (order_date);
CREATE INDEX IF NOT EXISTS idx_orders_status      ON orders (order_status);
CREATE INDEX IF NOT EXISTS idx_orders_contractor  ON orders (contractor_name);
CREATE INDEX IF NOT EXISTS idx_orders_sum_date    ON orders (order_date, sum);
CREATE INDEX IF NOT EXISTS idx_orders_needs_detail ON orders (detail_hash) WHERE detail_hash IS NULL;

-- ── Позиции ЗАКАЗА (order_nomenclatures + order_services) ──
-- Замещаются целиком при каждом успешном обновлении деталей.
CREATE TABLE IF NOT EXISTS order_items (
    id          BIGSERIAL PRIMARY KEY,
    orders_id   BIGINT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    kind        TEXT NOT NULL DEFAULT 'nomenclature',  -- nomenclature | service
    id_1c       TEXT,
    code_1c     TEXT,
    name        TEXT,
    group_name  TEXT,
    unit        TEXT,
    quantity    NUMERIC(12,3),
    price       NUMERIC(12,2),
    discount_pct NUMERIC(5,2),
    discount_price NUMERIC(12,2),
    total       NUMERIC(14,2),
    position    INTEGER,
    fetched_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_order_items_orders  ON order_items (orders_id);
CREATE INDEX IF NOT EXISTS idx_order_items_name    ON order_items (name);

-- ── Позиции ОТГРУЗКИ/реализации (demand.demand_nomenclatures + demand_services) ──
CREATE TABLE IF NOT EXISTS demand_items (
    id          BIGSERIAL PRIMARY KEY,
    orders_id   BIGINT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    demand_id   BIGINT,
    kind        TEXT NOT NULL DEFAULT 'nomenclature',
    id_1c       TEXT,
    code_1c     TEXT,
    name        TEXT,
    group_name  TEXT,
    unit        TEXT,
    quantity    NUMERIC(12,3),
    price       NUMERIC(12,2),
    discount_pct NUMERIC(5,2),
    discount_price NUMERIC(12,2),
    total       NUMERIC(14,2),
    position    INTEGER,
    fetched_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_demand_items_orders ON demand_items (orders_id);

-- ── Отгрузки (из списка: shipment_info; из деталей: delivery_orders/shipment_processes) ──
CREATE TABLE IF NOT EXISTS shipments (
    id              BIGSERIAL PRIMARY KEY,
    orders_id       BIGINT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    shipment_number TEXT,
    state           TEXT,
    driver_name     TEXT,
    driver_phone    TEXT,
    source          TEXT NOT NULL,                 -- list | detail
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE NULLS NOT DISTINCT (orders_id, shipment_number, source)
);
CREATE INDEX IF NOT EXISTS idx_shipments_orders ON shipments (orders_id);

-- ── Ежедневный срез статусов: сравнение периодов, "сколько висел в статусе" ──
CREATE TABLE IF NOT EXISTS order_status_history (
    id             BIGSERIAL PRIMARY KEY,
    orders_id      BIGINT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    snapshot_date  DATE   NOT NULL,
    order_status   TEXT,
    payment_status TEXT,
    sale_status    TEXT,
    sum            NUMERIC(14,2),
    weight         INTEGER,
    fetched_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (orders_id, snapshot_date)
);
CREATE INDEX IF NOT EXISTS idx_osh_date    ON order_status_history (snapshot_date);
CREATE INDEX IF NOT EXISTS idx_osh_status  ON order_status_history (order_status);


-- ── Этап 1: приём всего, что умеет API (см. docs/GRANDLINE_API.md) ──

-- Справочник групп номенклатуры (921) — сначала, на него ссылается nomenclature_full.
CREATE TABLE IF NOT EXISTS nomenclature_groups (
    id_1c               TEXT PRIMARY KEY,
    code_1c             TEXT,
    name                TEXT,
    manufacturing_points JSONB,
    is_deleted          BOOLEAN NOT NULL DEFAULT false,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Полный каталог 231k: аналитика по цвету/толщине/поверхности, не по строке-имени.
CREATE TABLE IF NOT EXISTS nomenclature_full (
    id_1c                TEXT PRIMARY KEY,
    code_1c              TEXT,
    full_name            TEXT,
    kind                 TEXT,               -- Продукция | Товары | Инвентарь...
    group_id_1c          TEXT REFERENCES nomenclature_groups(id_1c),
    group_name           TEXT,               -- денормализация для быстрых вью
    color                TEXT,
    surface              TEXT,
    thickness            TEXT,
    foil                 TEXT,
    weight               NUMERIC(10,3),
    tnved                TEXT,
    quantity_unit        TEXT,
    size_unit            TEXT,
    amount_unit          TEXT,
    weight_unit          TEXT,
    is_deleted           BOOLEAN NOT NULL DEFAULT false,
    first_seen           DATE NOT NULL DEFAULT CURRENT_DATE,
    last_seen            DATE NOT NULL DEFAULT CURRENT_DATE,
    raw                  JSONB
);
CREATE INDEX IF NOT EXISTS idx_nomfull_group  ON nomenclature_full (group_id_1c);
CREATE INDEX IF NOT EXISTS idx_nomfull_code   ON nomenclature_full (code_1c);
CREATE INDEX IF NOT EXISTS idx_nomfull_kind   ON nomenclature_full (kind);

-- Снапшот остатков: (товар, склад, тип) × дата. Динамика наличия + прогноз поставок.
CREATE TABLE IF NOT EXISTS remnants_snapshots (
    id              BIGSERIAL PRIMARY KEY,
    nomenclature_id TEXT NOT NULL,
    storage_id      TEXT,                     -- гуид склада/фабрики из ключа словаря
    kind            TEXT NOT NULL,            -- metall | goods
    qty             INTEGER NOT NULL DEFAULT 0,
    delivery_date   DATE,                     -- из delivery_time (если был)
    snapshot_date   DATE NOT NULL DEFAULT CURRENT_DATE,
    UNIQUE NULLS NOT DISTINCT (nomenclature_id, storage_id, kind, snapshot_date)
);
CREATE INDEX IF NOT EXISTS idx_rem_snap_nom  ON remnants_snapshots (nomenclature_id);
CREATE INDEX IF NOT EXISTS idx_rem_snap_date ON remnants_snapshots (snapshot_date);

-- История цен: одна строка на (товар, склад, соглашение, версию цены).
CREATE TABLE IF NOT EXISTS prices_history (
    id              BIGSERIAL PRIMARY KEY,
    nomenclature_id TEXT NOT NULL,
    branch_id_1c    TEXT NOT NULL,
    agreement_id_1c TEXT NOT NULL,
    price           NUMERIC(12,2),
    discount_pct    NUMERIC(5,2),
    discount_price  NUMERIC(12,2),
    version_date    TIMESTAMPTZ NOT NULL,     -- версия цены от поставщика
    first_seen      DATE NOT NULL DEFAULT CURRENT_DATE,
    last_seen       DATE NOT NULL DEFAULT CURRENT_DATE,
    UNIQUE NULLS NOT DISTINCT (nomenclature_id, branch_id_1c, agreement_id_1c, price, discount_pct, discount_price)
);
CREATE INDEX IF NOT EXISTS idx_prices_nom  ON prices_history (nomenclature_id);
CREATE INDEX IF NOT EXISTS idx_prices_vd   ON prices_history (nomenclature_id, version_date);

-- Реализации (счета/накладные) — фактическая выручка, 1:N к заказу.
CREATE TABLE IF NOT EXISTS sales (
    id              BIGSERIAL PRIMARY KEY,
    orders_id       BIGINT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    id_1c           TEXT,
    number          TEXT,
    sales_date      TIMESTAMPTZ,
    ware_sum        NUMERIC(14,2),
    service_sum     NUMERIC(14,2),
    total_sum       NUMERIC(14,2),
    posted          BOOLEAN,
    deletion_mark   BOOLEAN NOT NULL DEFAULT false,
    subcontractor   TEXT,
    kind            TEXT NOT NULL DEFAULT 'sale',   -- sale | correction
    raw             JSONB,
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE NULLS NOT DISTINCT (orders_id, id_1c, kind)
);
CREATE INDEX IF NOT EXISTS idx_sales_orders ON sales (orders_id);
CREATE INDEX IF NOT EXISTS idx_sales_date   ON sales (sales_date);

-- Ссылки на файлы/фото товара (сами файлы не качаем — толькоURL + дата проверки).
CREATE TABLE IF NOT EXISTS files (
    id              BIGSERIAL PRIMARY KEY,
    nomenclature_id TEXT NOT NULL,
    file_type       TEXT,                     -- «Изображение товара» | …
    url             TEXT NOT NULL,
    checked_at      DATE NOT NULL DEFAULT CURRENT_DATE,
    UNIQUE (nomenclature_id, url)
);
CREATE INDEX IF NOT EXISTS idx_files_nom ON files (nomenclature_id);

-- Справочник марок автомобилей (для отгрузок).
CREATE TABLE IF NOT EXISTS vehicle_brands (
    id_1c      TEXT PRIMARY KEY,
    name       TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── Журнал синхронизаций ──
CREATE TABLE IF NOT EXISTS sync_log (
    id               BIGSERIAL PRIMARY KEY,
    started_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at      TIMESTAMPTZ,
    mode             TEXT NOT NULL,               -- daily | backfill | enrich
    orders_seen      INTEGER,
    details_fetched  INTEGER,
    details_skipped  INTEGER,
    items_upserted   INTEGER,
    errors           INTEGER,
    error_detail     TEXT
);

-- ── A2: полнотекст-поиск (ILIKE '%...%') через pg_trgm ──
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX IF NOT EXISTS idx_orders_contractor_trgm ON orders USING gin (contractor_name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_number_trgm           ON orders USING gin (number gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_nomfull_name_trgm     ON nomenclature_full USING gin (full_name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_nom_group_name_trgm   ON nomenclature USING gin (group_name gin_trgm_ops);

-- ── A5: точечные индексы под топ-запросы сайта ──
CREATE INDEX IF NOT EXISTS idx_rem_kind_qty ON remnants_snapshots (kind, qty DESC) WHERE kind = 'metall';
CREATE INDEX IF NOT EXISTS idx_rem_kind_goods_qty ON remnants_snapshots (kind, qty DESC) WHERE kind = 'goods';
CREATE INDEX IF NOT EXISTS idx_rem_delivery ON remnants_snapshots (kind, delivery_date) WHERE kind = 'delivery';
