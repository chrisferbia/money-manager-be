from pathlib import Path
import sqlite3

import pytest
from fastapi import Request

from auth import require_subject


pytestmark = pytest.mark.integration


def _workspace(database, subject):
    cursor = database.connection.execute("INSERT INTO users (auth_subject) VALUES (?)", (subject,))
    user_id = cursor.lastrowid
    cursor = database.connection.execute(
        "INSERT INTO workspaces (owner_user_id, name) VALUES (?, 'Personal')", (user_id,)
    )
    database.connection.commit()
    return cursor.lastrowid


def _call(client, method, path, workspace_id, **kwargs):
    return client.request(method, path, headers={"X-Test-Workspace": str(workspace_id)}, **kwargs)


def test_workspace_provisioning_is_idempotent_and_does_not_claim_demo(inprocess_app):
    from app import app

    database, client = inprocess_app
    app.dependency_overrides[require_subject] = lambda: "clerk_user_new"
    try:
        first = client.post("/me/bootstrap")
        second = client.post("/me/bootstrap")
        assert first.status_code == second.status_code == 200
        workspace_id = first.json()["workspace_id"]
        assert workspace_id != 1
        assert second.json()["workspace_id"] == workspace_id
        assert database.connection.execute(
            "SELECT owner_user_id FROM workspaces WHERE id = 1"
        ).fetchone()[0] is None
        assert _call(client, "GET", "/accounts", workspace_id).json() == []
        assert len(_call(client, "GET", "/categories", workspace_id).json()) == 10
    finally:
        app.dependency_overrides.pop(require_subject, None)


def test_guessed_ids_and_cross_workspace_references_are_rejected(inprocess_app):
    database, client = inprocess_app
    alice = _workspace(database, "alice")
    bob = _workspace(database, "bob")
    a_account = _call(client, "POST", "/accounts", alice, json={"name": "Cash", "type": "cash"}).json()
    b_account = _call(client, "POST", "/accounts", bob, json={"name": "Cash", "type": "cash"}).json()
    assert a_account["id"] != b_account["id"]
    a_category = _call(client, "POST", "/categories", alice, json={"name": "Food", "type": "expense"}).json()
    b_category = _call(client, "POST", "/categories", bob, json={"name": "Food", "type": "expense"}).json()
    a_tx = _call(client, "POST", "/transactions", alice, json={
        "type": "expense", "account_id": a_account["id"],
        "category_id": a_category["id"], "amount": 30000, "description": "Alice lunch",
    }).json()

    for path in (f"/accounts/{a_account['id']}", f"/categories/{a_category['id']}", f"/transactions/{a_tx['id']}"):
        assert _call(client, "GET", path, bob).status_code == 404
    assert _call(client, "GET", "/transactions", bob).json() == []
    assert _call(client, "GET", "/transactions/descriptions?q=Alice", bob).json() == []
    assert _call(client, "GET", "/reports/expenses-by-category", bob).json() == []
    assert _call(client, "GET", "/accounts", alice).json()[0]["id"] == a_account["id"]
    assert _call(client, "GET", "/accounts", bob).json()[0]["id"] == b_account["id"]

    assert _call(client, "POST", "/transactions", bob, json={
        "type": "expense", "account_id": a_account["id"],
        "category_id": b_category["id"], "amount": 100,
    }).status_code == 404
    assert _call(client, "POST", "/transactions", bob, json={
        "type": "expense", "account_id": b_account["id"],
        "category_id": a_category["id"], "amount": 100,
    }).status_code == 404
    assert _call(client, "POST", "/transfers", bob, json={
        "type": "transfer", "account_id": b_account["id"],
        "related_account_id": a_account["id"], "amount": 100,
    }).status_code == 404
    assert _call(client, "PATCH", f"/transactions/{a_tx['id']}", bob, json={"amount": 1}).status_code == 404
    assert _call(client, "DELETE", f"/transactions/{a_tx['id']}", bob).status_code == 404
    assert _call(client, "GET", "/ui/transactions", bob).status_code == 200
    assert "Alice lunch" not in _call(client, "GET", "/ui/transactions", bob).text


def test_legacy_migration_keeps_demo_unowned_and_enforces_tenant_foreign_keys():
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript("""
        CREATE TABLE accounts (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, type TEXT NOT NULL,
            valuation_mode TEXT NOT NULL DEFAULT 'ledger', sequence INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE categories (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, type TEXT NOT NULL,
            sequence INTEGER NOT NULL DEFAULT 0, monthly_budget INTEGER,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE transactions (id INTEGER PRIMARY KEY, type TEXT NOT NULL,
            account_id INTEGER NOT NULL REFERENCES accounts(id), category_id INTEGER REFERENCES categories(id),
            related_account_id INTEGER REFERENCES accounts(id), amount INTEGER NOT NULL,
            description TEXT, counterparty TEXT, occurred_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, transaction_subtype TEXT, source_message_id TEXT);
        CREATE TABLE email_imports (id INTEGER PRIMARY KEY, message_id TEXT UNIQUE, sender TEXT, recipient TEXT,
            subject TEXT, received_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, status TEXT NOT NULL,
            reason TEXT, raw_size INTEGER, transaction_id INTEGER REFERENCES transactions(id) ON DELETE SET NULL,
            reference_number TEXT, transaction_subtype TEXT);
        CREATE TABLE crypto_holdings (id INTEGER PRIMARY KEY, account_id INTEGER NOT NULL REFERENCES accounts(id),
            coin_id TEXT NOT NULL, name TEXT NOT NULL, symbol TEXT NOT NULL, quantity TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(account_id, coin_id));
        CREATE TABLE crypto_prices (coin_id TEXT PRIMARY KEY, price_idr TEXT NOT NULL,
            provider_updated_at TEXT, fetched_at TEXT NOT NULL);
        INSERT INTO accounts (id, name, type) VALUES (5, 'Demo Cash', 'cash');
        INSERT INTO categories (id, name, type) VALUES (7, 'Demo Food', 'expense');
        INSERT INTO transactions (id, type, account_id, category_id, amount) VALUES (9, 'expense', 5, 7, 100);
        INSERT INTO email_imports (id, message_id, status, transaction_id) VALUES (4, 'demo-mail', 'imported', 9);
    """)
    migration = Path(__file__).parents[1] / "migrations" / "0010_saas_workspaces.sql"
    connection.executescript(migration.read_text())
    assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    assert connection.execute("SELECT workspace_id FROM transactions WHERE id = 9").fetchone()[0] == 1
    assert connection.execute("SELECT owner_user_id FROM workspaces WHERE id = 1").fetchone()[0] is None
    connection.execute("INSERT INTO users (auth_subject) VALUES ('new-user')")
    connection.execute("INSERT INTO workspaces (id, owner_user_id, name) VALUES (2, 1, 'Personal')")
    connection.execute("INSERT INTO accounts (workspace_id, name, type) VALUES (2, 'Demo Cash', 'cash')")
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute("INSERT INTO transactions (workspace_id, type, account_id, amount) VALUES (2, 'income', 5, 1)")
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute("INSERT INTO email_imports (workspace_id, message_id, status, transaction_id) VALUES (2, 'foreign-mail', 'imported', 9)")
    connection.execute("DELETE FROM transactions WHERE id = 9")
    assert connection.execute(
        "SELECT workspace_id, transaction_id FROM email_imports WHERE id = 4"
    ).fetchone() == (1, None)
