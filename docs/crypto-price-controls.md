# Crypto price expiry and manual refresh

Each workspace stores its own `crypto_price_expiry_minutes` setting (integer,
1–1440 minutes; default 10). Signed-in users can read or update only their own
setting through `GET` / `PATCH /settings/crypto-prices`.

This controls cache freshness, not a scheduled task. Existing account/holding
reads fetch expired quotes on demand. While open, the holdings panel checks every
60 seconds. Price status uses the same workspace preference. Quotes remain shared
public market data; refreshing a coin can also make its cached quote newer for
other workspaces. No holdings or preferences are shared.

The 60-second UI check is a backend cache read, not an unconditional CoinGecko
price fetch. Page loads, focus/reconnect checks, quantity edits, and saved settings
never force fresh prices to be fetched again. Automatic requests send only expired
or missing coin quotes to the provider; each successful quote starts a new expiry
window. A coin with no cached quote requires an initial fetch. The manual-refresh
endpoint is the only cache-expiry bypass.

`POST /accounts/{account_id}/holdings/refresh-prices` verifies account ownership
and crypto valuation, then forces a provider fetch for every distinct coin held
across the signed-in user's workspace, even if the quotes have not expired.
Duplicate coins across wallets are requested once (provider batches remain at
100 coins). Other users' holdings and unused cached coins are not requested.
It returns workspace-wide requested/refreshed counts, failed coin IDs, selected
account `holdings` and `holdings_by_account` for all workspace crypto accounts.
The frontend updates every wallet's holdings cache directly from this response,
without separate holdings fetches, and reloads account balances. The button is
labelled "Refresh all crypto prices" and can be used from an empty wallet when
other wallets hold coins. Quantities and transactions are untouched. Automatic
expiry, per-coin timestamps and failure retry behavior are unchanged. No new
database migration is required. Deploy the backend before the frontend.
Signed-out demo users
cannot access either mutation endpoint.

Provider failure never overwrites a quote or its fetch timestamp. Total failure
returns 503 with a retry message; partial success reports failed coins. A valid
provider response can have the same price as before: force refresh bypasses our
cache, but does not guarantee that the provider's own quote has changed.

## Diagnosing provider failures

Redeploy the updated backend before reproducing a live error. Stream logs for
the actual backend Worker named in the browser refresh request, not necessarily
the `private` environment. If Wrangler reports code 10007, check the selected
Cloudflare account and deployed Worker name; no app logs can be read until those
match.

Refresh failures emit warning logs prefixed with `Crypto price refresh`:

- `mode=manual` or `mode=automatic` identifies the trigger.
- `reason=http_error`, `http_status`, and optional numeric `provider_code`
  distinguish provider HTTP errors. Codes come from CoinGecko, not our 503.
- `api_key_configured=True/False` reports presence only, never the key value.
- `reason=invalid_json` identifies a non-JSON successful response.
- `reason=transport_or_runtime_error` and `exception_type` identify failures
  before a usable provider response was available.
- `invalid_response_shape`, `missing_quote`, `invalid_quote_shape`,
  `invalid_idr_price`, or `invalid_provider_timestamp` explain rejected quotes,
  including partial failures.

For example (illustrative, not a diagnosis of a real live request):

```text
Crypto price refresh failed: provider=coingecko mode=manual reason=http_error http_status=429 provider_code=None api_key_configured=False exception_type=MarketProviderError; cached prices kept
```

No provider response bodies, request URLs, coin IDs, holdings, account/workspace
IDs, API-key values, or raw exception messages/tracebacks are included in these
price-refresh logs. Rejected quotes are summarized once per provider batch. Fresh
cache reads and successful fetches do not produce warning logs. Refresh timing,
the frontend 503 message, and stale-cache preservation are unchanged. No new
database migration is required for logging.

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
fictional BTC and ETH across two wallets. Its simulated provider changes BTC
from 1 billion to 1.2 billion IDR and ETH from 50 to 60 million IDR. A single
manual request therefore updates both wallets, including their shared BTC
quote. It uses no real database or external market request.
