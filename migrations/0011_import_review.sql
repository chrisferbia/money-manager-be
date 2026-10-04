-- Pending BCA uploads and user-approved category rules. No raw email is stored.
CREATE TABLE IF NOT EXISTS import_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id INTEGER NOT NULL REFERENCES workspaces(id),
    account_id INTEGER,
    message_id TEXT,
    fingerprint TEXT NOT NULL,
    reference_number TEXT,
    direction TEXT NOT NULL CHECK(direction IN ('income', 'expense')),
    amount INTEGER NOT NULL CHECK(amount > 0),
    counterparty TEXT,
    merchant_key TEXT NOT NULL,
    description TEXT,
    occurred_at TEXT NOT NULL,
    transaction_subtype TEXT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'imported', 'dismissed')),
    transaction_id INTEGER REFERENCES transactions(id) ON DELETE SET NULL,
    received_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    reviewed_at TEXT,
    UNIQUE(workspace_id, message_id),
    UNIQUE(workspace_id, fingerprint),
    UNIQUE(workspace_id, reference_number, direction, occurred_at),
    FOREIGN KEY(workspace_id, account_id) REFERENCES accounts(workspace_id, id)
);
CREATE INDEX IF NOT EXISTS import_reviews_workspace_status
    ON import_reviews(workspace_id, status, id DESC);

CREATE TRIGGER IF NOT EXISTS import_reviews_workspace_insert
BEFORE INSERT ON import_reviews
WHEN NEW.transaction_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM transactions WHERE id = NEW.transaction_id AND workspace_id = NEW.workspace_id
)
BEGIN
    SELECT RAISE(ABORT, 'Import transaction belongs to another workspace');
END;
CREATE TRIGGER IF NOT EXISTS import_reviews_workspace_update
BEFORE UPDATE OF transaction_id, workspace_id ON import_reviews
WHEN NEW.transaction_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM transactions WHERE id = NEW.transaction_id AND workspace_id = NEW.workspace_id
)
BEGIN
    SELECT RAISE(ABORT, 'Import transaction belongs to another workspace');
END;
CREATE TRIGGER IF NOT EXISTS import_reviews_account_deleted
BEFORE DELETE ON accounts
BEGIN
    UPDATE import_reviews SET account_id = NULL
    WHERE workspace_id = OLD.workspace_id AND account_id = OLD.id;
END;

CREATE TABLE IF NOT EXISTS merchant_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id INTEGER NOT NULL REFERENCES workspaces(id),
    merchant_key TEXT NOT NULL,
    merchant_name TEXT NOT NULL,
    direction TEXT NOT NULL CHECK(direction IN ('income', 'expense')),
    category_id INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(workspace_id, merchant_key, direction),
    FOREIGN KEY(workspace_id, category_id) REFERENCES categories(workspace_id, id) ON DELETE CASCADE
);
