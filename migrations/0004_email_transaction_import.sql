ALTER TABLE transactions ADD COLUMN source_message_id TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS transactions_source_message_id_unique
    ON transactions(source_message_id)
    WHERE source_message_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS email_imports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id TEXT UNIQUE,
    sender TEXT,
    recipient TEXT,
    subject TEXT,
    received_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status TEXT NOT NULL,
    reason TEXT,
    raw_size INTEGER,
    transaction_id INTEGER REFERENCES transactions(id) ON DELETE SET NULL,
    reference_number TEXT
);
