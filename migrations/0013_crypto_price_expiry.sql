-- Per-user cache expiry. Existing and new workspaces retain the 10-minute default.
ALTER TABLE workspaces ADD COLUMN crypto_price_expiry_minutes INTEGER NOT NULL
    DEFAULT 10 CHECK(crypto_price_expiry_minutes BETWEEN 1 AND 1440);
