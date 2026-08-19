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

UPDATE transactions
SET category_id = (
    SELECT id FROM categories
    WHERE name = CASE transactions.type
        WHEN 'income' THEN 'Other Income'
        WHEN 'expense' THEN 'Other Expense'
    END
    AND type = transactions.type
)
WHERE type IN ('income', 'expense') AND category_id IS NULL;
