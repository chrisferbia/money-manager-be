CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    type TEXT NOT NULL,
    sequence INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT OR IGNORE INTO accounts (name, type, sequence) VALUES
    ('Cash Wallet', 'cash', 1),
    ('Main Checking', 'bank', 2),
    ('Emergency Savings', 'savings', 3),
    ('Credit Card', 'credit_card', 4),
    ('PayPal', 'e_wallet', 5),
    ('Investment Portfolio', 'investment', 6),
    ('Student Loan', 'loan', 7),
    ('Home Mortgage', 'mortgage', 8);

CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    type TEXT NOT NULL DEFAULT 'expense',
    sequence INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT OR IGNORE INTO categories (name, type, sequence) VALUES
    ('Salary', 'income', 1),
    ('Freelance', 'income', 2),
    ('Business', 'income', 3),
    ('Investment', 'income', 4),
    ('Gift', 'income', 5),
    ('Other Income', 'income', 6),
    ('Housing', 'expense', 7),
    ('Food', 'expense', 8),
    ('Transportation', 'expense', 9),
    ('Utilities', 'expense', 10),
    ('Healthcare', 'expense', 11),
    ('Shopping', 'expense', 12),
    ('Entertainment', 'expense', 13),
    ('Education', 'expense', 14),
    ('Personal Care', 'expense', 15),
    ('Debt Payment', 'expense', 16),
    ('Fees & Charges', 'expense', 17),
    ('Other Expense', 'expense', 18);

CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,
    account_id INTEGER NOT NULL REFERENCES accounts(id),
    category_id INTEGER REFERENCES categories(id),
    related_account_id INTEGER REFERENCES accounts(id),
    amount INTEGER NOT NULL,
    description TEXT,
    counterparty TEXT,
    occurred_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    transaction_subtype TEXT,
    source_message_id TEXT
);

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
    reference_number TEXT,
    transaction_subtype TEXT
);
