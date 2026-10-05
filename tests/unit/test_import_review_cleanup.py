import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from email_import import process_email
from fake_d1 import FakeD1

pytestmark = pytest.mark.unit
ROOT = Path(__file__).parents[2]
SCHEMA = (ROOT / "db_init.sql").read_text()
OLD_MIGRATION = (ROOT / "migrations/0011_import_review.sql").read_text()
CLEANUP = (ROOT / "migrations/0012_remove_import_review.sql").read_text()
RAW = (ROOT / "tests/fixtures/bca-review-fictional.eml").read_bytes()
PROTECTED_TABLES = ("users", "workspaces", "accounts", "categories", "transactions", "email_imports", "crypto_holdings", "crypto_prices")


def protected_snapshot(database):
    return {table: [tuple(row) for row in database.connection.execute(f"SELECT * FROM {table} ORDER BY 1")] for table in PROTECTED_TABLES}


def objects(database):
    return [tuple(row) for row in database.connection.execute(
        "SELECT type, name, tbl_name, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
    )]


def test_cleanup_preserves_owned_workspace_ledger_and_auto_import_history():
    database = FakeD1(SCHEMA)
    conn = database.connection
    conn.executescript(OLD_MIGRATION)
    conn.execute("INSERT INTO users (auth_subject) VALUES ('fictional-owner')")
    conn.execute("UPDATE workspaces SET owner_user_id = 1 WHERE id = 1")
    account_id = conn.execute("INSERT INTO accounts (workspace_id,name,type) VALUES (1,'BCA','bank')").lastrowid
    conn.execute("UPDATE categories SET name = 'Other' WHERE name = 'Other Expense' AND workspace_id = 1")
    category_id = conn.execute("SELECT id FROM categories WHERE name = 'Other' AND workspace_id = 1").fetchone()[0]
    tx = conn.execute("INSERT INTO transactions (workspace_id,type,account_id,category_id,amount) VALUES (1,'expense',?,?,35000)", (account_id, category_id)).lastrowid
    conn.execute("INSERT INTO email_imports (workspace_id,message_id,status,transaction_id) VALUES (1,'fictional-auto','imported',?)", (tx,))
    for status, transaction_id in (("pending", None), ("imported", tx), ("dismissed", None)):
        conn.execute("INSERT INTO import_reviews (workspace_id,account_id,fingerprint,direction,amount,merchant_key,occurred_at,status,transaction_id) VALUES (1,?,?,'expense',35000,'fictional','2026-10-04T05:00:00Z',?,?)", (account_id, status, status, transaction_id))
    conn.execute("INSERT INTO merchant_rules (workspace_id,merchant_key,merchant_name,direction,category_id) VALUES (1,'fictional','Fictional','expense',?)", (category_id,))
    conn.commit()
    before = protected_snapshot(database)
    expected_objects = [obj for obj in objects(database) if not obj[1].startswith('import_reviews') and obj[1] != 'merchant_rules']
    conn.executescript(CLEANUP)
    assert protected_snapshot(database) == before
    assert objects(database) == expected_objects
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    # Check the account trigger was removed too: deleting a new empty account
    # must not fail with 'no such table: import_reviews'.
    empty = conn.execute("INSERT INTO accounts (workspace_id,name,type) VALUES (1,'Disposable fictional account','bank')").lastrowid
    conn.execute("DELETE FROM accounts WHERE id = ?", (empty,))
    conn.commit()
    assert protected_snapshot(database) == before
    conn.executescript(CLEANUP)
    assert protected_snapshot(database) == before
    # Real automatic importer still works and de-duplicates, without review tables.
    message = SimpleNamespace(raw=RAW, headers={}, to="fictional@example.invalid", rawSize=len(RAW))
    env = SimpleNamespace(money_manager=database)
    asyncio.run(process_email(message, env))
    asyncio.run(process_email(message, env))
    assert conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 2
    row = conn.execute("SELECT t.amount,c.name FROM transactions t JOIN categories c ON c.id=t.category_id WHERE source_message_id IS NOT NULL").fetchone()
    assert tuple(row) == (35000, "Other")
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_cleanup_is_safe_on_fresh_database_and_matches_upgraded_schema():
    fresh = FakeD1(SCHEMA)
    upgraded = FakeD1(SCHEMA)
    upgraded.connection.executescript(OLD_MIGRATION)
    upgraded.connection.executescript(CLEANUP)
    assert objects(upgraded) == objects(fresh)
    before = protected_snapshot(fresh)
    fresh.connection.executescript(CLEANUP)
    fresh.connection.executescript(CLEANUP)
    assert protected_snapshot(fresh) == before
    assert objects(upgraded) == objects(fresh)
