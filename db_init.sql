CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    type TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT OR IGNORE INTO accounts (name, type) VALUES
    ('Cash Wallet', 'cash'),
    ('Main Checking', 'bank'),
    ('Emergency Savings', 'savings'),
    ('Credit Card', 'credit_card'),
    ('PayPal', 'e_wallet'),
    ('Investment Portfolio', 'investment'),
    ('Student Loan', 'loan'),
    ('Home Mortgage', 'mortgage');

CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    type TEXT NOT NULL DEFAULT 'expense',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT OR IGNORE INTO categories (name, type) VALUES
    ('Salary', 'income'),
    ('Freelance', 'income'),
    ('Business', 'income'),
    ('Investment', 'income'),
    ('Gift', 'income'),
    ('Other Income', 'income'),
    ('Housing', 'expense'),
    ('Food', 'expense'),
    ('Transportation', 'expense'),
    ('Utilities', 'expense'),
    ('Healthcare', 'expense'),
    ('Shopping', 'expense'),
    ('Entertainment', 'expense'),
    ('Education', 'expense'),
    ('Personal Care', 'expense'),
    ('Debt Payment', 'expense'),
    ('Fees & Charges', 'expense'),
    ('Other Expense', 'expense');

CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,
    account_id INTEGER NOT NULL REFERENCES accounts(id),
    category_id INTEGER REFERENCES categories(id),
    related_account_id INTEGER REFERENCES accounts(id),
    amount INTEGER NOT NULL,
    description TEXT,
    occurred_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
