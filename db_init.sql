CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    auth_subject TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS workspaces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_user_id INTEGER UNIQUE REFERENCES users(id),
    name TEXT NOT NULL,
    crypto_price_expiry_minutes INTEGER NOT NULL DEFAULT 10
        CHECK(crypto_price_expiry_minutes BETWEEN 1 AND 1440),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Existing public demo rows remain unowned and inaccessible to signed-in users.
INSERT OR IGNORE INTO workspaces (id, owner_user_id, name) VALUES (1, NULL, 'Legacy demo');

CREATE TABLE IF NOT EXISTS accounts (
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

INSERT OR IGNORE INTO accounts (workspace_id, name, type, sequence) VALUES
    (1, 'Cash Wallet', 'cash', 1),
    (1, 'Main Checking', 'bank', 2),
    (1, 'Emergency Savings', 'savings', 3),
    (1, 'Credit Card', 'credit_card', 4),
    (1, 'PayPal', 'e_wallet', 5),
    (1, 'Investment Portfolio', 'investment', 6),
    (1, 'Student Loan', 'loan', 7),
    (1, 'Home Mortgage', 'mortgage', 8);

CREATE TABLE IF NOT EXISTS categories (
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

INSERT OR IGNORE INTO categories (workspace_id, name, type, sequence) VALUES
    (1, 'Salary', 'income', 1),
    (1, 'Freelance', 'income', 2),
    (1, 'Business', 'income', 3),
    (1, 'Investment', 'income', 4),
    (1, 'Gift', 'income', 5),
    (1, 'Other Income', 'income', 6),
    (1, 'Housing', 'expense', 7),
    (1, 'Food', 'expense', 8),
    (1, 'Transportation', 'expense', 9),
    (1, 'Utilities', 'expense', 10),
    (1, 'Healthcare', 'expense', 11),
    (1, 'Shopping', 'expense', 12),
    (1, 'Entertainment', 'expense', 13),
    (1, 'Education', 'expense', 14),
    (1, 'Personal Care', 'expense', 15),
    (1, 'Debt Payment', 'expense', 16),
    (1, 'Fees & Charges', 'expense', 17),
    (1, 'Other Expense', 'expense', 18);

CREATE TABLE IF NOT EXISTS transactions (
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
    FOREIGN KEY(workspace_id, account_id) REFERENCES accounts(workspace_id, id),
    FOREIGN KEY(workspace_id, category_id) REFERENCES categories(workspace_id, id),
    FOREIGN KEY(workspace_id, related_account_id) REFERENCES accounts(workspace_id, id)
);

CREATE UNIQUE INDEX IF NOT EXISTS transactions_source_message_id_unique
    ON transactions(workspace_id, source_message_id)
    WHERE source_message_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS transactions_workspace_date ON transactions(workspace_id, occurred_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS email_imports (
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
    FOREIGN KEY(transaction_id) REFERENCES transactions(id) ON DELETE SET NULL
);

CREATE TRIGGER IF NOT EXISTS email_imports_workspace_insert
BEFORE INSERT ON email_imports
WHEN NEW.transaction_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM transactions WHERE id = NEW.transaction_id AND workspace_id = NEW.workspace_id
)
BEGIN
    SELECT RAISE(ABORT, 'Email import transaction belongs to another workspace');
END;

CREATE TRIGGER IF NOT EXISTS email_imports_workspace_update
BEFORE UPDATE OF transaction_id, workspace_id ON email_imports
WHEN NEW.transaction_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM transactions WHERE id = NEW.transaction_id AND workspace_id = NEW.workspace_id
)
BEGIN
    SELECT RAISE(ABORT, 'Email import transaction belongs to another workspace');
END;

CREATE TABLE IF NOT EXISTS crypto_holdings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id INTEGER NOT NULL REFERENCES workspaces(id),
    account_id INTEGER NOT NULL,
    coin_id TEXT NOT NULL,
    name TEXT NOT NULL,
    symbol TEXT NOT NULL,
    quantity TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(account_id, coin_id),
    FOREIGN KEY(workspace_id, account_id) REFERENCES accounts(workspace_id, id)
);

CREATE TABLE IF NOT EXISTS crypto_prices (
    coin_id TEXT PRIMARY KEY,
    price_idr TEXT NOT NULL,
    provider_updated_at TEXT,
    fetched_at TEXT NOT NULL
);
