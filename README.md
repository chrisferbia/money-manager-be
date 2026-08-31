# Hello World Example

Warning: Python support in Workers is experimental and things will break. This
example is meant for reference only right now; you should be prepared to update
your code between now and official release time as APIs may change.

## How to Run

First ensure that `uv` is installed:
https://docs.astral.sh/uv/getting-started/installation/#standalone-installer

Now, if you run `uv run pywrangler dev` within this directory, it should use the config
in `wrangler.jsonc` to run the example.

Manual deploy: `uv run pywrangler deploy`

uv run pywrangler d1 execute money-manager --remote --file db_init.sql

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


