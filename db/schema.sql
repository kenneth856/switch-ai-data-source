-- 1. Vendors (from NetSuite)
CREATE TABLE IF NOT EXISTS vendors (
    id          TEXT PRIMARY KEY,
    companyname TEXT,
    email       TEXT,
    phone       TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- 2. Items / Ingredients (from NetSuite)
CREATE TABLE IF NOT EXISTS items (
    id          TEXT PRIMARY KEY,
    itemid      TEXT,
    displayname TEXT,
    weight      NUMERIC,
    weightunit  TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- 3. Transactions / Purchase Orders (from NetSuite)
CREATE TABLE IF NOT EXISTS transactions (
    id           TEXT PRIMARY KEY,
    type         TEXT,
    status       TEXT,
    trandate     DATE,
    entity       TEXT,       -- vendor id
    currency     TEXT,
    foreigntotal NUMERIC,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

-- 4. Transaction Lines (from NetSuite)
CREATE TABLE IF NOT EXISTS transaction_lines (
    transaction         TEXT,
    linesequencenumber  INTEGER,
    item                TEXT,
    quantity            NUMERIC,
    rate                NUMERIC,
    amount              NUMERIC,
    memo                TEXT,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (transaction, linesequencenumber)
);

-- 5. Fuel Prices — Brent Crude (from Yahoo Finance via scrape_external.py)
CREATE TABLE IF NOT EXISTS fuel_prices (
    date                    DATE PRIMARY KEY,
    brent_crude_usd_per_bbl NUMERIC,
    created_at              TIMESTAMPTZ DEFAULT NOW()
);

-- 6. Exchange Rates (from open.er-api.com via scrape_external.py)
CREATE TABLE IF NOT EXISTS exchange_rates (
    date        DATE PRIMARY KEY,
    aud_per_usd NUMERIC,
    cny_per_usd NUMERIC,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- 7. Freight Predictions — stores every prediction made by the AI
--    so we can track accuracy over time and retrain the model
CREATE TABLE IF NOT EXISTS freight_predictions (
    id                   UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    origin               TEXT,
    destination          TEXT,
    carrier              TEXT,
    weight_kg            NUMERIC,
    predicted_cost       NUMERIC,
    predicted_days       INTEGER,
    on_time_probability  NUMERIC,
    currency             TEXT DEFAULT 'USD',
    predicted_at         TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- Enable Row Level Security (RLS) — required for Supabase
-- The service_role key bypasses RLS so the loader can write freely.
-- ============================================================
ALTER TABLE vendors           ENABLE ROW LEVEL SECURITY;
ALTER TABLE items             ENABLE ROW LEVEL SECURITY;
ALTER TABLE transactions      ENABLE ROW LEVEL SECURITY;
ALTER TABLE transaction_lines ENABLE ROW LEVEL SECURITY;
ALTER TABLE fuel_prices       ENABLE ROW LEVEL SECURITY;
ALTER TABLE exchange_rates    ENABLE ROW LEVEL SECURITY;
ALTER TABLE freight_predictions ENABLE ROW LEVEL SECURITY;
