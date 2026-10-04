# BCA email format tester

Signed-in users can open **Settings → Email format tester** and choose a BCA `.eml` file (up to 1 MB), or try the fictional sample. The authenticated `POST /email-tools/bca/preview` endpoint uses the same `parse_bca_email` function as automatic inbound imports.

The response displays amount in IDR, date, direction, subtype, merchant, description, reference, status, sender, subject and message ID. Failed status and missing message ID produce warnings. Malformed or unsupported formats produce parsing errors. Forwarded senders are allowed like the existing automatic parser, with an authenticity warning. A successful preview verifies the format only, not delivery, authenticity, account/category existence or duplicate detection.

No raw email, parsed record, import log, merchant rule or transaction is stored. Repeated tests are safe and do not affect balances or reports. Preview responses use `Cache-Control: no-store`. The browser holds results only until the user chooses another file, starts another test, or leaves Settings.

The former `/imports` staging, approval, history and rule endpoints are no longer mounted. Existing import-review tables and migration history are preserved without accessing or deleting any deployed data. The tester does not require those tables or any new migration.

## Automatic imports are unchanged

The Worker email handler still directly calls the existing automatic importer for workspace 1 and its BCA account, using expense category `Other` and income category `Other Income`. It continues to record delivery/import outcomes separately in `email_imports` and create supported successful transactions automatically. The tester does not receive or intercept inbound emails.

## Local verification (fictional data only)

1. From the backend root: `python tests/manual/import_preview.py` (test dependencies and `uvicorn` required).
2. From the frontend root: `npx vite --config tests/manual/vite.config.ts`.
3. Open `http://127.0.0.1:5179/tests/manual/import-preview.html#settings` and try the fictional sample.

These loopback-only test adapters use an in-memory database, not Cloudflare D1. Production authentication still uses Clerk.

`python tests/manual/worker_import_smoke.py` checks parsing and no ledger changes using the explicitly local binding in `wrangler.import-review-test.jsonc`. That configuration retains its historical name and never targets the private or public remote D1 database.
