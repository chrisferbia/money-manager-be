-- Retire the manual review inbox. Deploy the preview-only app before applying.
-- Back up the target database first: pending reviews and merchant rules are removed.
-- Accounts, categories, transactions, email_imports and crypto data are unchanged.

-- This trigger is attached to accounts, not import_reviews. Remove it first so
-- future account deletions cannot reference a table that no longer exists.
DROP TRIGGER IF EXISTS import_reviews_account_deleted;
DROP TRIGGER IF EXISTS import_reviews_workspace_insert;
DROP TRIGGER IF EXISTS import_reviews_workspace_update;
DROP INDEX IF EXISTS import_reviews_workspace_status;
DROP TABLE IF EXISTS merchant_rules;
DROP TABLE IF EXISTS import_reviews;
