# Money Manager Backend

A personal finance application built with Python, FastAPI, and Cloudflare Workers, using Cloudflare D1 for storage. It provides a JSON API, a server-rendered web interface, and an email handler that imports supported BCA transaction notifications.

## Features

- Create, edit, delete, and reorder accounts and income/expense categories.
- Record income, expenses, and transfers between accounts, with counterparties, descriptions, and transaction dates.
- Calculate account balances from transaction history and summarize expenses by category.
- View a dashboard with balances, income, expenses, net change, and recent transactions. Filter activity by month or date range; balances remain all-time totals.
- Import supported BCA emails with Message-ID deduplication and an import audit log.
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

**Both bindings currently set `"remote": true`.** Running `dev` with these settings connects to remote D1, so application writes change the database used by the corresponding deployed Worker.

For local development with local data, set `"remote": false` (or remove the property) on the selected binding in `wrangler.jsonc`. The default binding is under `d1_databases`; the private binding is under `env.private.d1_databases`.

If deploying to your own Cloudflare account, replace the database names/IDs and Worker names with your own configuration.

### 3. Initialize a fresh local database

```powershell
# Default environment
npx wrangler d1 execute money-manager --local --file db_init.sql

# Or: private environment
npx wrangler d1 execute private-money-manager --env private --local --file db_init.sql
```

`db_init.sql` creates the current schema and seeds eight accounts and eighteen categories. It does not seed transactions or record migration history.

**Do not apply all historical migrations after initialization.** The migration chain assumes an existing schema, and `db_init.sql` already includes columns added by migrations `0001` through `0007`. For an existing database, follow the [schema and migration caveat](docs/d1-commands.md#existing-schema-and-initialization-caveat) before applying changes.

### 4. Start the Worker

```powershell
# Default environment
uv run pywrangler dev --port 8787

# Or: private environment
uv run pywrangler dev --env private --port 8787
```

Open [the dashboard](http://localhost:8787) or [interactive API documentation](http://localhost:8787/docs). `npm run dev` and `npm start` also start the default environment.

If Windows development fails with missing vendored dependencies such as `jinja2`, see the [PyWrangler Windows troubleshooting guide](docs/pywrangler-windows-vendoring-fix.md).

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

The Worker's email entrypoint processes supported BCA notification formats, including transfers, QRIS payments, virtual-account payments, pocket transfers, and cardless cash withdrawals. Imported records use `income` or `expense`, with a separate `transaction_subtype`; email pocket transfers and withdrawals are currently recorded as expenses.

To use imports:

1. Configure Cloudflare Email Routing to deliver messages to the intended Worker.
2. Create an account named **`BCA`** in that Worker's database.
3. Ensure an income category named **`Other Income`** and an expense category named **`Other`** exist.

The initialization script includes `Other Income`, but creates neither the `BCA` account nor the `Other` expense category (`Other Expense` is a different name).

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

Real Worker smoke tests initialize local D1 and start PyWrangler. **Set the default binding's `remote` property to `false` before running these tests**, since the server uses `wrangler.jsonc` and the persistence test creates an account.

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

Deploy the selected environment:

```powershell
# Public Worker
uv run pywrangler deploy

# Private Worker
uv run pywrangler deploy --env private
```

`npm run deploy` deploys the default public Worker. For Cloudflare Workers Builds, use the matching command above as each Worker's deploy command. The private Worker requires `--env private`.

Deployment does not initialize D1 or apply migrations. See the [D1 command guide](docs/d1-commands.md) for remote initialization, queries, migration management, and backups.

The application implements no authentication or per-user data isolation. `private` selects a separate Worker and database; it does not add access control. CORS currently allows `http://localhost:5173` and HTTPS subdomains of `azamines.workers.dev`, as configured in `src/app.py`.

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
