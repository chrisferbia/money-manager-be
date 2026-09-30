-- Apply only after 0009_crypto_holdings.sql. Existing records are retained in
-- an unowned demo workspace (id 1); no sign-up can claim them automatically.
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    auth_subject TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE workspaces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_user_id INTEGER UNIQUE REFERENCES users(id),
    name TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
INSERT INTO workspaces (id, owner_user_id, name) VALUES (1, NULL, 'Legacy demo');

CREATE TABLE accounts_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id INTEGER NOT NULL REFERENCES workspaces(id),
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    valuation_mode TEXT NOT NULL DEFAULT 'ledger' CHECK(valuation_mode IN ('ledger', 'crypto')),
    sequence INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(workspace_id, name),
    UNIQUE(workspace_id, id)
);
INSERT INTO accounts_new (id, workspace_id, name, type, valuation_mode, sequence, created_at)
SELECT id, 1, name, type, valuation_mode, sequence, created_at FROM accounts;

CREATE TABLE categories_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id INTEGER NOT NULL REFERENCES workspaces(id),
    name TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'expense',
    sequence INTEGER NOT NULL DEFAULT 0,
    monthly_budget INTEGER CHECK(monthly_budget IS NULL OR monthly_budget > 0),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(workspace_id, name),
    UNIQUE(workspace_id, id)
);
INSERT INTO categories_new (id, workspace_id, name, type, sequence, monthly_budget, created_at)
SELECT id, 1, name, type, sequence, monthly_budget, created_at FROM categories;

CREATE TABLE transactions_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id INTEGER NOT NULL REFERENCES workspaces(id),
    type TEXT NOT NULL,
    account_id INTEGER NOT NULL,
    category_id INTEGER,
    related_account_id INTEGER,
    amount INTEGER NOT NULL,
    description TEXT,
    counterparty TEXT,
    occurred_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    transaction_subtype TEXT,
    source_message_id TEXT,
    UNIQUE(workspace_id, id),
    FOREIGN KEY(workspace_id, account_id) REFERENCES accounts_new(workspace_id, id),
    FOREIGN KEY(workspace_id, category_id) REFERENCES categories_new(workspace_id, id),
    FOREIGN KEY(workspace_id, related_account_id) REFERENCES accounts_new(workspace_id, id)
);
INSERT INTO transactions_new (id, workspace_id, type, account_id, category_id, related_account_id, amount, description, counterparty, occurred_at, created_at, transaction_subtype, source_message_id)
SELECT id, 1, type, account_id, category_id, related_account_id, amount, description, counterparty, occurred_at, created_at, transaction_subtype, source_message_id FROM transactions;

CREATE TABLE email_imports_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id INTEGER NOT NULL REFERENCES workspaces(id),
    message_id TEXT,
    sender TEXT,
    recipient TEXT,
    subject TEXT,
    received_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status TEXT NOT NULL,
    reason TEXT,
    raw_size INTEGER,
    transaction_id INTEGER,
    reference_number TEXT,
    transaction_subtype TEXT,
    UNIQUE(workspace_id, message_id),
    FOREIGN KEY(transaction_id) REFERENCES transactions_new(id) ON DELETE SET NULL
);
INSERT INTO email_imports_new (id, workspace_id, message_id, sender, recipient, subject, received_at, status, reason, raw_size, transaction_id, reference_number, transaction_subtype)
SELECT id, 1, message_id, sender, recipient, subject, received_at, status, reason, raw_size, transaction_id, reference_number, transaction_subtype FROM email_imports;

CREATE TABLE crypto_holdings_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id INTEGER NOT NULL REFERENCES workspaces(id),
    account_id INTEGER NOT NULL,
    coin_id TEXT NOT NULL,
    name TEXT NOT NULL,
    symbol TEXT NOT NULL,
    quantity TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(account_id, coin_id),
    FOREIGN KEY(workspace_id, account_id) REFERENCES accounts_new(workspace_id, id)
);
INSERT INTO crypto_holdings_new (id, workspace_id, account_id, coin_id, name, symbol, quantity, created_at)
SELECT id, 1, account_id, coin_id, name, symbol, quantity, created_at FROM crypto_holdings;

DROP TABLE email_imports;
DROP TABLE crypto_holdings;
DROP TABLE transactions;
DROP TABLE categories;
DROP TABLE accounts;
ALTER TABLE accounts_new RENAME TO accounts;
ALTER TABLE categories_new RENAME TO categories;
ALTER TABLE transactions_new RENAME TO transactions;
ALTER TABLE email_imports_new RENAME TO email_imports;
ALTER TABLE crypto_holdings_new RENAME TO crypto_holdings;

CREATE TRIGGER email_imports_workspace_insert
BEFORE INSERT ON email_imports
WHEN NEW.transaction_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM transactions WHERE id = NEW.transaction_id AND workspace_id = NEW.workspace_id
)
BEGIN
    SELECT RAISE(ABORT, 'Email import transaction belongs to another workspace');
END;

CREATE TRIGGER email_imports_workspace_update
BEFORE UPDATE OF transaction_id, workspace_id ON email_imports
WHEN NEW.transaction_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM transactions WHERE id = NEW.transaction_id AND workspace_id = NEW.workspace_id
)
BEGIN
    SELECT RAISE(ABORT, 'Email import transaction belongs to another workspace');
END;

CREATE UNIQUE INDEX transactions_source_message_id_unique
    ON transactions(workspace_id, source_message_id)
    WHERE source_message_id IS NOT NULL;
CREATE INDEX transactions_workspace_date ON transactions(workspace_id, occurred_at DESC, id DESC);
