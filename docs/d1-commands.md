# Cloudflare D1 Commands

This project has two D1 databases:

- `money-manager` is used by the default environment and `money-manager-be`.
- `private-money-manager` is used by the `private` environment and
  `private-money-manager-be`.

The `money_manager` binding name is the same in application code; Wrangler maps it to
the database configured for the selected environment.

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

Remote database:

```powershell
npx wrangler d1 execute money-manager --remote --command "SELECT * FROM accounts"
```

Local database:

```powershell
npx wrangler d1 execute money-manager --local --command "SELECT * FROM accounts"
```

Execute a SQL file:

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

npx wrangler d1 execute private-money-manager --remote --file db_init.sql
npx wrangler d1 execute money-manager --remote --file db_init.sql

Create a migration:

```powershell
npx wrangler d1 migrations create money-manager add-feature
```

List unapplied remote migrations:

```powershell
npx wrangler d1 migrations list money-manager --remote
```

Apply remote migrations:

```powershell
npx wrangler d1 migrations apply money-manager --remote
```

Apply local migrations:

```powershell
npx wrangler d1 migrations apply money-manager --local
```

Use `migrations apply` for migration files so Wrangler records them in
`d1_migrations`. Do not use `d1 execute --file` for a migration unless you also
intend to manage the migration history manually.

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

`--remote` changes the production database. Use it carefully.
