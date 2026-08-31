ALTER TABLE transactions ADD COLUMN transaction_subtype TEXT;

ALTER TABLE email_imports ADD COLUMN transaction_subtype TEXT;
