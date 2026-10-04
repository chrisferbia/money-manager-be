# BCA import review

Signed-in users can upload an original BCA notification `.eml` (up to 1 MB) from the frontend **Import inbox**. Select an account that records transactions. Successful, supported IDR notifications enter a pending queue; balances and reports change only after approval. The file's sender header identifies the supported format, not cryptographic proof of a bank transaction. Raw email, recipient and account-number fields are not stored.

Saved merchant rules take priority. Otherwise, consistent categories from that user's previously approved imports provide a tentative suggestion. Conflicting history, generic merchant names, cash withdrawals and pocket transfers require manual review. Users explicitly choose whether to save a rule. Rules can be edited or removed without rewriting earlier transactions. Cash/pocket transfers can be skipped and recorded using the normal transfer form.

Approving creates the transaction and optional rule in one D1 batch. Repeated uploads are matched within the workspace by message ID, bank reference/date/direction or a fingerprint of parsed transaction fields. Approval retries reuse the same transaction; skipped notifications remain in history to prevent re-import. Re-approving an import whose transaction was later deleted does not recreate it.

## Database setup

New local databases use `db_init.sql`. Existing databases need the additive migration `migrations/0011_import_review.sql` before using the inbox. No remote database or deployed Worker is changed by this implementation. Apply the migration only to the public database when deploying this feature; the private database stays outside this task.

```powershell
npx wrangler d1 execute money-manager --remote --file migrations/0011_import_review.sql
```

The existing inbound email handler separately calls the automatic importer for owned workspace 1 in the connected database, using expense category `Other` and income category `Other Income`. Keep the existing email routing rule pointed at the private Worker. Manual review uses the category selected by the user (including `Other`) or a matching saved rule; it does not hard-code `Other Expense`. Future per-user inbound review needs authenticated sender checks and recipient-to-workspace/account routing before calling `stage_bca_email`.

## Local UI verification

The frontend includes a fictional sample notification under `public/samples/`. It creates a ledger record only if the user approves it.

For repeatable UI verification using only an in-memory database:

1. From the backend root, run `python tests/manual/import_preview.py` with the project's test dependencies and `uvicorn` installed.
2. From the frontend root, run `npx vite --config tests/manual/vite.config.ts`.
3. Open `http://127.0.0.1:5179/tests/manual/import-preview.html#imports`.

These test adapters bind to loopback and are not production entrypoints. The production build and app continue using Clerk authentication.

For a real Worker/D1 smoke check, run `python tests/manual/worker_import_smoke.py`. It uses `wrangler.import-review-test.jsonc`, an explicitly local D1 binding, disposable test users and locally generated session tokens. It checks D1 batch approval, duplicate retries, saved-rule suggestions and skip. Existing installed Worker Python packages are required, as for ordinary local Worker development.
