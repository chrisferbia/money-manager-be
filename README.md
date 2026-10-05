# Money Manager Backend

A personal finance application built with Python, FastAPI, and Cloudflare Workers, using Cloudflare D1 for storage. The public Worker now requires Clerk sign-in and gives each user one isolated personal workspace.

## Features

- Create, edit, delete, and reorder accounts and income/expense categories.
- Record income, expenses, and transfers between accounts, with counterparties, descriptions, and transaction dates.
- Calculate account balances from transaction history and summarize expenses by category.
- Track manually entered crypto quantities in Investment accounts, with cached CoinGecko IDR prices and market-value balances.
- View a dashboard with balances, income, expenses, net change, and recent transactions. Filter activity by month or date range; balances remain all-time totals.
- Keep accounts, categories, transactions, holdings, and reports isolated by signed-in user.
- Deploy separate public and private Workers, each connected to its own D1 database.

## Stack

- **Runtime:** Cloudflare Python Workers, with PyWrangler for development and deployment.
- **HTTP:** FastAPI with Pydantic request/response models.
- **UI:** Jinja2 templates served by the same Worker.
- **Database:** Cloudflare D1 through the `money_manager` binding.
- **Tooling:** `uv`, npm/Wrangler, pytest, and pytest-cov.

## Getting started

Run commands from the repository root. You need Python 3.12 or newer, `uv`, and Node.js/npm. Cloudflare authentication is required when accessing remote D1 or deploying.

### 1. Install dependencies

```powershell
uv sync
npm install
```

### 2. Choose your database target

The current [Wrangler configuration](wrangler.jsonc) defines:

| Environment | Worker | D1 database | Binding |
| --- | --- | --- | --- |
| Default (public) | `money-manager-be` | `money-manager` | `money_manager` |
| `private` | `private-money-manager-be` | `private-money-manager` | `money_manager` |

**Both bindings currently set `"remote": true`.** Running `dev` with these settings connects to remote D1, so application writes change the database used by the corresponding deployed Worker. The private database is outside this SaaS migration; do not run the new migration or deploy this version with `--env private`.

For local development with local data, set `"remote": false` (or remove the property) on the selected binding in `wrangler.jsonc`. The default binding is under `d1_databases`; the private binding is under `env.private.d1_databases`.

If deploying to your own Cloudflare account, replace the database names/IDs and Worker names with your own configuration.

### 3. Initialize a fresh local database

```powershell
# Default environment
npx wrangler d1 execute money-manager --local --file db_init.sql

# Or: private environment
npx wrangler d1 execute private-money-manager --env private --local --file db_init.sql
```

`db_init.sql` creates the current schema and an unowned demo workspace (ID 1) with sample accounts and categories. A newly signed-in user gets a separate empty personal workspace and starter categories. It does not seed transactions or record migration history.

**Do not apply all historical migrations after initialization.** The migration chain assumes an existing schema, and `db_init.sql` already includes columns added by migrations `0001` through `0007`. For an existing database, follow the [schema and migration caveat](docs/d1-commands.md#existing-schema-and-initialization-caveat) before applying changes.

### 4. Configure sign-in for the public Worker

Configure these backend Worker bindings before using the protected API:

| Name | Value |
| --- | --- |
| `CLERK_ISSUER` | `https://topical-meerkat-6998.clerk.accounts.dev` |
| `CLERK_AUTHORIZED_PARTIES` | `http://localhost:5173,https://money-manager-fe.azamines.workers.dev` |
| `CLERK_JWT_KEY` | The Clerk instance's **public** PEM verification key, with newlines preserved or encoded as `\\n` |

Never configure or commit the Clerk secret key in either project. The backend accepts only RS256-signed tokens from this issuer and one of the listed frontend origins. Missing configuration returns 503; missing or invalid tokens return 401. `POST /me/bootstrap` creates the signed-in user's one-person workspace, and the frontend calls it before loading private data.

For the **existing public D1 only**, take a backup and review `migrations/0010_saas_workspaces.sql` before applying it once. It moves existing public demo rows into unowned demo workspace 1 and adds workspace-scoped keys. It does not touch the private D1. Do not deploy the new backend before that migration, because its queries require the new columns. Do not apply this migration to a fresh database initialized from the current `db_init.sql`.

### 5. Start the Worker

```powershell
# Default environment
uv run pywrangler dev --port 8787

# Or: private environment
uv run pywrangler dev --env private --port 8787
```

The API now requires a signed Clerk session. `npm run dev` and `npm start` also start the default environment. For local testing, change the public D1 binding to local (`"remote": false`) first; otherwise development requests can write to remote D1.

If Windows development fails with missing vendored dependencies such as `jinja2`, see the [PyWrangler Windows troubleshooting guide](docs/pywrangler-windows-vendoring-fix.md).

### Crypto holdings setup

Apply `migrations/0009_crypto_holdings.sql` **once** to each existing D1 database before deploying a frontend that uses crypto tracking. Fresh databases initialized with `db_init.sql` already include the schema. Check the selected Wrangler environment and whether the command targets local or remote D1 before running it; this repository's development bindings currently point to remote D1.

The backend calls CoinGecko for coin search and IDR prices. Public requests can work without a key, but may be rate-limited. Optionally configure `COINGECKO_API_KEY` as a backend Worker secret (a CoinGecko Demo API key); never put it in the frontend's `BACKEND_URL` or `VITE_API_URL`. Prices are cached in D1 for ten minutes. A failed refresh retains the last known price and marks it stale; a holding without any known price makes its account balance unavailable rather than silently counting it as zero.

Crypto-enabled accounts are valued from holdings, not their historical transaction balance. Enabling this on an existing Investment account with a nonzero ledger balance requires explicit confirmation. New transactions and transfers to/from crypto-enabled accounts are rejected; update the source account separately when adding a holding. Existing transactions remain stored for audit, but are excluded from that account's displayed market value.

## Web interface

| Path | Page |
| --- | --- |
| `/` | Dashboard with month/date filters |
| `/ui/accounts` | Account management |
| `/ui/categories` | Category management |
| `/ui/transactions` | Transaction management |
| `/ui/reports/expenses-by-category` | Expense totals by category |
| `/docs` | Swagger UI |
| `/redoc` | ReDoc API reference |
| `/openapi.json` | OpenAPI schema |

## JSON API

Routes are served directly from the root, without an `/api` prefix.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET`, `POST` | `/accounts` | List or create accounts |
| `GET`, `PATCH`, `DELETE` | `/accounts/{account_id}` | Read, update, or delete an account |
| `GET` | `/accounts/{account_id}/balance` | Calculate an account's balance |
| `GET`, `POST` | `/categories` | List or create categories |
| `GET`, `PATCH`, `DELETE` | `/categories/{category_id}` | Read, update, or delete a category |
| `GET`, `POST` | `/transactions` | List or create transactions |
| `GET` | `/transactions/descriptions` | Suggest distinct saved descriptions; accepts `q` and `limit` ([API contract](docs/transaction-description-api.md)) |
| `GET`, `PATCH`, `DELETE` | `/transactions/{transaction_id}` | Read, update, or delete a transaction |
| `POST` | `/transfers` | Create a transaction with `type: "transfer"` |
| `GET` | `/reports/expenses-by-category` | Summarize expenses, optionally by date range |

### Query parameters

- `GET /accounts?include_balance=true` includes calculated balances.
- `GET /transactions` accepts `account_id`, `category_id`, `type`, `from`, and `to`. An account filter includes both incoming and outgoing transfers. Results are ordered by `occurred_at` descending, then ID descending.
- `GET /reports/expenses-by-category` accepts `from` and `to` and sorts category totals from largest to smallest.

API date filters compare stored timestamps directly with inclusive bounds. Use full UTC timestamps such as `2026-09-01T00:00:00Z` and `2026-09-30T23:59:59Z`.

### Transaction rules

- Amounts are positive integers. The email importer and demo data use whole Indonesian rupiah; the API has no currency field or conversion.
- Expenses require an expense category. Income categories are optional, but must have type `income` when supplied.
- Transfers require different source (`account_id`) and destination (`related_account_id`) accounts and cannot have a category. They subtract from the source balance and add to the destination balance.
- `occurred_at` is normalized to UTC. Missing or invalid values fall back to the current time; timestamps without a timezone are treated as UTC.
- Account and category names must be unique within their respective tables. Records referenced by transactions cannot be deleted.
- Accounts and categories support a positive, one-based `sequence` for ordering. Account types are free-form strings; category types are `income` or `expense` and cannot be changed through category updates.

For example, send this JSON to `POST /transactions`, using existing account and expense-category IDs:

```json
{
  "type": "expense",
  "account_id": 1,
  "category_id": 8,
  "amount": 35000,
  "counterparty": "Coffee shop",
  "description": "Lunch",
  "occurred_at": "2026-09-12T05:00:00Z"
}
```

## BCA email imports

The Worker email entrypoint calls the existing automatic importer. It uses workspace **1** in the Worker's connected database, not a workspace inferred from the sender. The existing Cloudflare Email Routing rule must deliver incoming mail only to the intended private Worker. This is the personal email-import workflow, not per-user inbound routing or Smart import review.

The Worker's email entrypoint processes supported BCA notification formats, including transfers, QRIS payments, virtual-account payments, pocket transfers, and cardless cash withdrawals. Imported records use `income` or `expense`, with a separate `transaction_subtype`; email pocket transfers and withdrawals are currently recorded as expenses.

To use imports:

1. Configure Cloudflare Email Routing to deliver messages to the intended Worker.
2. Create an account named **`BCA`** in that Worker's database.
3. Ensure an income category named **`Other Income`** and an expense category named **`Other`** exist in workspace 1.


Messages need a Message-ID and a supported successful transaction status. The importer stores outcomes and reasons in `email_imports`, links successful imports to transactions, and logs results to the Worker console. Unsupported or invalid messages are recorded for review; missing account/category mappings produce failed imports. Repeated Message-IDs are skipped, including previously logged failures; there is no automatic retry workflow.

Sender validation is currently disabled in `src/email_import.py` for forwarded-email testing. The importer does not currently enforce the BCA sender address.

## Tests

```powershell
# Default suite: unit tests and in-process API/UI integration tests
uv run pytest

# Unit tests only
uv run pytest -m unit

# Coverage for the default suite
uv run pytest --cov=src --cov-report=term-missing
```

The default suite excludes the `worker` marker. Integration tests use FastAPI's test client with an in-memory SQLite D1 adapter; they do not start PyWrangler.

Real Worker smoke tests initialize an isolated local D1 and start PyWrangler with a temporary test signing key. **Set the default binding's `remote` property to `false` before running these tests.** The tests skip otherwise, and the private D1 is never used. Restore the setting afterward.

```powershell
uv run pytest -m worker
uv run pytest -m "unit or integration or worker"
```

The Worker fixture invokes `npx.cmd`, so it currently assumes Windows.

## Deployment

Check or establish Cloudflare authentication:

```powershell
npx wrangler whoami
npx wrangler login
```

After migrating and configuring only the public database/Worker, deploy the default environment:

```powershell
# Public Worker
uv run pywrangler deploy

# deploy directly with worker name
uv run pywrangler deploy --env private --name money-manager-be
```

`npm run deploy` deploys the default public Worker.

Deployment does not initialize D1 or apply migrations. See the [D1 command guide](docs/d1-commands.md) for remote initialization, queries, migration management, and backups.

The HTTP API requires Clerk session tokens and scopes data to each user's workspace. CORS allows `http://localhost:5173` and `https://money-manager-fe.azamines.workers.dev`, as configured in `src/app.py`.

## Worker logs

Stream logs from the deployed public Worker in a readable format:

```powershell
npx wrangler tail money-manager-be --format pretty
```

## Project layout

```text
src/
  entry.py          Worker HTTP and email entrypoints
  app.py            FastAPI application and CORS configuration
  api.py            JSON API routes
  ui.py             Web routes and form handlers
  templates.py      Embedded Jinja2 templates
  models.py         Pydantic models
  domain.py         Transaction validation rules
  db.py             D1 queries, balances, and reports
  email_import.py   BCA email parsing and import processing
tests/              Unit, in-process integration, and Worker smoke tests
migrations/         Historical schema changes and seed/backfill migrations
seeds/              Optional fictional demo transactions
specs/              Feature specifications
docs/               D1 operations and Windows troubleshooting
db_init.sql         Current schema and default account/category seeds
wrangler.jsonc      Worker environments and D1 bindings
pyproject.toml      Python dependencies and pytest configuration
package.json        npm scripts and Wrangler dependency
```

The optional `seeds/demo-2026q3.sql` contains fictional activity from July through September 2026. It looks up accounts and categories by name, including accounts `BCA`, `Cash`, and `Pocket`, which are absent from the default initialization. Rows with missing required mappings are skipped, and stable source IDs prevent duplicate inserts on reruns.
