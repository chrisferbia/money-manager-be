"""Public demo exposes fictional ledger reads, never a mutation or another workspace."""

import pytest


@pytest.mark.integration
def test_anonymous_demo_is_read_only_and_scoped(inprocess_app):
    database, client = inprocess_app
    database.reset()
    database.connection.execute(
        "INSERT INTO accounts (id, workspace_id, name, type) VALUES (101, 1, 'Demo Cash', 'cash')"
    )
    database.connection.execute("INSERT INTO users (id, auth_subject) VALUES (5, 'other-user')")
    database.connection.execute(
        "INSERT INTO workspaces (id, owner_user_id, name) VALUES (5, 5, 'Private')"
    )
    database.connection.execute(
        "INSERT INTO accounts (id, workspace_id, name, type) VALUES (105, 5, 'Private Cash', 'cash')"
    )
    database.connection.commit()

    response = client.get("/demo/accounts")
    assert response.status_code == 200
    assert [account["name"] for account in response.json()] == ["Demo Cash"]
    assert client.get("/demo/metadata").json() == {"latest_transaction_at": None}
    assert client.get("/demo/categories").status_code == 200
    assert client.get("/demo/transactions").status_code == 200
    assert client.get("/demo/reports/expenses-by-category").status_code == 200
    assert client.post("/demo/accounts", json={"name": "Bad", "type": "cash"}).status_code == 405
    assert client.patch("/demo/accounts/101", json={"name": "Bad"}).status_code == 404
    assert client.get("/demo/accounts/105").status_code == 404
    assert client.get("/demo/transactions/descriptions").status_code == 404
    assert client.get("/demo/crypto/search?q=btc").status_code == 404


@pytest.mark.integration
def test_demo_stops_if_reserved_workspace_is_claimed(inprocess_app):
    database, client = inprocess_app
    database.reset()
    database.connection.execute("INSERT INTO users (id, auth_subject) VALUES (7, 'claimed')")
    database.connection.execute("UPDATE workspaces SET owner_user_id = 7 WHERE id = 1")
    database.connection.commit()
    assert client.get("/demo/accounts").status_code == 503
    database.connection.execute("UPDATE workspaces SET owner_user_id = NULL WHERE id = 1")
    database.connection.commit()
