# Crypto price expiry and manual refresh

Each workspace stores its own `crypto_price_expiry_minutes` setting (integer,
1–1440 minutes; default 10). Signed-in users can read or update only their own
setting through `GET` / `PATCH /settings/crypto-prices`.

This controls cache freshness, not a scheduled task. Existing account/holding
reads fetch expired quotes on demand. While open, the holdings panel checks every
60 seconds. Price status uses the same workspace preference. Quotes remain shared
public market data; refreshing a coin can also make its cached quote newer for
other workspaces. No holdings or preferences are shared.

`POST /accounts/{account_id}/holdings/refresh-prices` verifies account ownership
and crypto valuation, then forces a provider fetch for that account's coins,
even if the existing quotes have not expired. It returns requested/refreshed
counts, failed coin IDs and updated holdings. The frontend updates the account
balance too. Quantities and transactions are untouched. Signed-out demo users
cannot access either mutation endpoint.

Provider failure never overwrites a quote or its fetch timestamp. Total failure
returns 503 with a retry message; partial success reports failed coins. A valid
provider response can have the same price as before: force refresh bypasses our
cache, but does not guarantee that the provider's own quote has changed.

## Existing database deployment

Apply `migrations/0013_crypto_price_expiry.sql` to each intended existing database
before deploying this backend. Fresh databases use the updated `db_init.sql`.
Do not reinitialize an existing database. Back up the selected database first.

Check `PRAGMA table_info(workspaces)` before applying the migration; if the
column already exists, do not execute the ALTER again. Check that the migration
history reflects your actual schema before using a full migration runner. Some
environments have older schema changes applied manually: blindly running all
pending historical files can fail or recreate removed review tables.

For a targeted application (choose only the intended environment):

```powershell
# Public live D1
npx wrangler d1 execute money-manager --remote --file migrations/0013_crypto_price_expiry.sql
# Private live D1
npx wrangler d1 execute private-money-manager --env private --remote --file migrations/0013_crypto_price_expiry.sql
```

The targeted execute command does not register the file in `d1_migrations`.
After verifying the column, register the migration in the selected database's
migration history if using Wrangler-managed migrations. Do not run these remote
commands just to test the UI.

## Local verification

The regression suite covers workspace isolation, validation, exact expiry
boundaries, force-fetch of fresh cache, failure preservation and partial success.
`tests/manual/crypto_preview.py` provides a loopback-only in-memory adapter with
fictional BTC. Its simulated provider changes the price from 1 billion to
1.2 billion IDR; 0.01 BTC therefore changes from 10 to 12 million IDR. It uses no
real database or external market request.
