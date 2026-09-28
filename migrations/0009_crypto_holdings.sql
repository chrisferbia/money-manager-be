ALTER TABLE accounts ADD COLUMN valuation_mode TEXT NOT NULL DEFAULT 'ledger' CHECK(valuation_mode IN ('ledger', 'crypto'));

CREATE TABLE IF NOT EXISTS crypto_holdings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL REFERENCES accounts(id),
    coin_id TEXT NOT NULL,
    name TEXT NOT NULL,
    symbol TEXT NOT NULL,
    quantity TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(account_id, coin_id)
);

CREATE TABLE IF NOT EXISTS crypto_prices (
    coin_id TEXT PRIMARY KEY,
    price_idr TEXT NOT NULL,
    provider_updated_at TEXT,
    fetched_at TEXT NOT NULL
);
