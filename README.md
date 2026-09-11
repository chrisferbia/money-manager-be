# Hello World Example

Warning: Python support in Workers is experimental and things will break. This
example is meant for reference only right now; you should be prepared to update
your code between now and official release time as APIs may change.

## How to Run

First ensure that `uv` is installed:
https://docs.astral.sh/uv/getting-started/installation/#standalone-installer

Now, if you run `uv run pywrangler dev` within this directory, it should use the config
in `wrangler.jsonc` to run the public environment.

See [the D1 development and database guide](docs/d1-commands.md) for all four
public/private and local/remote combinations: starting development, running SELECT
queries, and listing/applying migrations. It also explains how a binding's
`"remote": true` setting affects local development.

## Deployments

This repository contains two backend Worker environments with separate D1 databases:

| Environment | Worker | D1 database |
| --- | --- | --- |
| default | `money-manager-be` | `money-manager` |
| `private` | `private-money-manager-be` | `private-money-manager` |

Deploy the public backend:

```powershell
uv run pywrangler deploy
```

Deploy the private backend:

```powershell
uv run pywrangler deploy --env private
```

When using Cloudflare Workers Builds, you do not need to run these commands manually.
Set the **Deploy command** in each connected Worker's **Settings > Builds** page:

- `money-manager-be`: `uv run pywrangler deploy`
- `private-money-manager-be`: `uv run pywrangler deploy --env private`

Cloudflare runs the selected command automatically after each Git push. The public
Worker uses the default configuration. The private Worker must use `--env private`;
otherwise it will deploy the default public Worker configuration. If non-production
branch builds are enabled, set the corresponding preview command to
`uv run pywrangler versions upload` or
`uv run pywrangler versions upload --env private`.

For a fresh remote database, initialize it separately. Read the
[migration setup caveat](docs/d1-commands.md#existing-schema-and-initialization-caveat)
before using initialization together with historical migrations:

```powershell
npx wrangler d1 execute private-money-manager --env private --remote --file db_init.sql
npx wrangler d1 execute money-manager --remote --file db_init.sql
```

The application code always uses the same binding name, `money_manager`. The binding
name is mapped to a different D1 database by each Wrangler environment.

## Test
Run Worker tests explicitly:
pytest -m worker
pytest -m "unit or integration or worker"

Test coverage
pytest --cov=src --cov-report=term-missing

## Cloudflare
Check current local Cloudflare authentication account
npx wrangler whoami

## Email Worker

The Worker logs incoming email metadata (sender, recipient, subject, message
ID, date, and size) to the Worker console. Configure Cloudflare Email Routing
to send an address on your domain to the `money-manager-be` Worker.


