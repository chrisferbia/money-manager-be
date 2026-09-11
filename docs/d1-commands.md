# Cloudflare D1 Commands

This project has two D1 databases:

- `money-manager` is used by the default environment and `money-manager-be`.
- `private-money-manager` is used by the `private` environment and
  `private-money-manager-be`.

The `money_manager` binding name is the same in application code; Wrangler maps it to
the database configured for the selected environment.

Run the commands below from the repository root. Each database has separate local
and remote data and migration history; they do not synchronize automatically.

## Start Development: Four Combinations

For either **local DB** command below, the selected `d1_databases` entry in
`wrangler.jsonc` must omit `"remote"` or set it to `false`. The private binding
currently has `"remote": true`; change it to `false` before using the private local
DB command. Otherwise, that command runs the backend locally against remote D1.

```powershell
# money-manager: local backend and local DB
uv run pywrangler dev --port 8787

# money-manager: Cloudflare preview backend and remote DB
uv run pywrangler dev --remote --port 8787

# private-money-manager: local backend and local DB (see binding setting above)
uv run pywrangler dev --env private --port 8787

# private-money-manager: Cloudflare preview backend and remote DB
uv run pywrangler dev --env private --remote --port 8787
```

Open http://localhost:8787. Stop the server with Ctrl+C before switching.
With `dev --remote`, the local server forwards requests to a development Worker
running on Cloudflare. This does not deploy changes to the live Worker, but writes
affect the connected remote database used by the deployed app.

To run the backend on your computer with remote D1 instead, set `"remote": true`
on the selected binding and run `dev` without `--remote`. The public binding is
at `d1_databases`; the private binding is at `env.private.d1_databases`.

The explicit `--local` and `--remote` flags on the D1 commands below choose their
database target independently of the development server. No dev server is needed.

## Authentication

```powershell
npx wrangler whoami
npx wrangler login
```

## Database Information

```powershell
npx wrangler d1 list
npx wrangler d1 info money-manager
```

## Execute SQL

Select from each of the four databases:

```powershell
# money-manager: local
npx wrangler d1 execute money-manager --local --command "SELECT * FROM accounts"

# money-manager: remote
npx wrangler d1 execute money-manager --remote --command "SELECT * FROM accounts"

# private-money-manager: local
npx wrangler d1 execute private-money-manager --env private --local --command "SELECT * FROM accounts"

# private-money-manager: remote
npx wrangler d1 execute private-money-manager --env private --remote --command "SELECT * FROM accounts"
```

Execute a SQL file (for fresh initialization, see the migration caveat below):

```powershell
npx wrangler d1 execute money-manager --remote --file db_init.sql
```

## Inspect Schema

```powershell
npx wrangler d1 execute money-manager --remote --command "SELECT name, sql FROM sqlite_master WHERE type='table'"
```

```powershell
npx wrangler d1 execute money-manager --remote --command "PRAGMA table_info(transactions)"
```

## Migrations

### Existing Schema and Initialization Caveat

Check the database schema and migration history before applying migrations:

- The first migration assumes tables already exist, so the migration chain cannot
  initialize an empty database by itself.
- `db_init.sql` creates the current schema, including columns added by historical
  migrations `0001` through `0007`. It does not record them in `d1_migrations`.
- Applying all historical migrations after `db_init.sql` can fail with duplicate
  column errors. Re-running `db_init.sql` is not an upgrade path for old tables.

If a database was initialized using `db_init.sql` or migrations were executed
manually, reconcile its actual schema, seed/backfill changes, and migration history
first. Only record an old migration as completed after verifying its changes are
already present. The commands below assume that history matches the database.

### Create Once, Apply Separately

Create a migration:

```powershell
npx wrangler d1 migrations create money-manager add-feature
```

Edit the generated SQL file in `migrations/`. Both environments share this folder;
create each migration once, test it locally, then apply it to each remote target.

List unapplied migrations for each database:

```powershell
npx wrangler d1 migrations list money-manager --local
npx wrangler d1 migrations list money-manager --remote
npx wrangler d1 migrations list private-money-manager --env private --local
npx wrangler d1 migrations list private-money-manager --env private --remote
```

Apply pending migrations for the selected database:

```powershell
# money-manager: local
npx wrangler d1 migrations apply money-manager --local

# money-manager: remote
npx wrangler d1 migrations apply money-manager --remote

# private-money-manager: local
npx wrangler d1 migrations apply private-money-manager --env private --local

# private-money-manager: remote
npx wrangler d1 migrations apply private-money-manager --env private --remote
```

Use `migrations apply` for migration files so Wrangler records them in
`d1_migrations`. Do not use `d1 execute --file` for a migration unless you also
intend to manage the migration history manually.
Each database tracks applied files separately. Deploying the Worker does not apply
these migrations. Run `migrations list` again to check what remains pending.

## Backup and Export

```powershell
npx wrangler d1 export money-manager --remote --output .\backup.sql
```

Export schema only:

```powershell
npx wrangler d1 export money-manager --remote --no-data --output .\schema.sql
```

## Time Travel

```powershell
npx wrangler d1 time-travel info money-manager --timestamp "2026-08-31T12:00:00Z"
```

Restoring is destructive:

```powershell
npx wrangler d1 time-travel restore money-manager --timestamp "2026-08-31T12:00:00Z"
```

## Useful Queries

```powershell
npx wrangler d1 execute money-manager --remote --command "SELECT * FROM accounts ORDER BY id"
```

```powershell
npx wrangler d1 execute money-manager --remote --command "SELECT * FROM categories ORDER BY type, name"
```

```powershell
npx wrangler d1 execute money-manager --remote --command "SELECT * FROM transactions ORDER BY occurred_at DESC"
```

```powershell
npx wrangler d1 execute money-manager --remote --command "SELECT * FROM email_imports ORDER BY id DESC"
```

`--remote` targets the Cloudflare database. SELECT queries read it; SQL writes and
migration commands change it.

## References

- [Cloudflare D1 local development](https://developers.cloudflare.com/d1/best-practices/local-development/)
- [Cloudflare D1 migrations](https://developers.cloudflare.com/d1/reference/migrations/)
