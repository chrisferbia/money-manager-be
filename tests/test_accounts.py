"""Tests for specs/0001-account-master.md."""

import requests
import pytest


pytestmark = pytest.mark.integration


def test_ac1_create_account_returns_201_with_id(dev_server):
    port = dev_server
    response = requests.post(
        f"http://localhost:{port}/accounts",
        json={"name": "AC1 Cash", "type": "cash"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "AC1 Cash"
    assert body["type"] == "cash"
    assert isinstance(body["id"], int)
    assert "created_at" in body


def test_ac2_duplicate_name_is_rejected(dev_server):
    port = dev_server
    first = requests.post(
        f"http://localhost:{port}/accounts",
        json={"name": "AC2 Duplicate", "type": "cash"},
    )
    assert first.status_code == 201

    second = requests.post(
        f"http://localhost:{port}/accounts",
        json={"name": "AC2 Duplicate", "type": "debit_card"},
    )
    assert 400 <= second.status_code < 500

    listing = requests.get(f"http://localhost:{port}/accounts")
    matches = [a for a in listing.json() if a["name"] == "AC2 Duplicate"]
    assert len(matches) == 1


def test_ac3_list_accounts_returns_created_accounts(dev_server):
    port = dev_server
    created = requests.post(
        f"http://localhost:{port}/accounts",
        json={"name": "AC3 Debit", "type": "debit_card"},
    ).json()

    listing = requests.get(f"http://localhost:{port}/accounts")
    assert listing.status_code == 200
    ids = [a["id"] for a in listing.json()]
    assert created["id"] in ids


def test_ac3_sequence_controls_account_order(dev_server):
    port = dev_server
    first = requests.post(
        f"http://localhost:{port}/accounts",
        json={"name": "AC3 First", "type": "cash"},
    ).json()
    second = requests.post(
        f"http://localhost:{port}/accounts",
        json={"name": "AC3 Second", "type": "cash"},
    ).json()
    third = requests.post(
        f"http://localhost:{port}/accounts",
        json={"name": "AC3 Third", "type": "cash"},
    ).json()

    moved = requests.patch(
        f"http://localhost:{port}/accounts/{third['id']}",
        json={"sequence": 1},
    )
    assert moved.status_code == 200
    assert moved.json()["sequence"] == 1

    listing = requests.get(f"http://localhost:{port}/accounts").json()
    assert [account["id"] for account in listing] == [third["id"], first["id"], second["id"]]
    assert [account["sequence"] for account in listing] == [1, 2, 3]


def test_ui_account_edit_updates_sequence(dev_server):
    port = dev_server
    first = requests.post(
        f"http://localhost:{port}/accounts",
        json={"name": "UI First", "type": "cash"},
    ).json()
    second = requests.post(
        f"http://localhost:{port}/accounts",
        json={"name": "UI Second", "type": "cash"},
    ).json()

    response = requests.post(
        f"http://localhost:{port}/ui/accounts/{second['id']}/edit",
        data={"name": second["name"], "type": second["type"], "sequence": "1"},
    )

    assert response.status_code == 200
    listing = requests.get(f"http://localhost:{port}/accounts").json()
    assert [account["id"] for account in listing] == [second["id"], first["id"]]


def test_ac3b_list_accounts_include_balance_returns_balances(dev_server):
    port = dev_server
    cash = requests.post(
        f"http://localhost:{port}/accounts",
        json={"name": "AC3 Balance Cash", "type": "cash"},
    ).json()
    debit = requests.post(
        f"http://localhost:{port}/accounts",
        json={"name": "AC3 Balance Debit", "type": "debit_card"},
    ).json()

    balance_listing = requests.get(f"http://localhost:{port}/accounts", params={"include_balance": "true"})
    assert balance_listing.status_code == 200
    rows = balance_listing.json()
    cash_row = next(row for row in rows if row["id"] == cash["id"])
    debit_row = next(row for row in rows if row["id"] == debit["id"])
    assert cash_row["balance"] == 0
    assert debit_row["balance"] == 0


def test_ac2_new_account_has_zero_balance(dev_server):
    port = dev_server
    account = requests.post(
        f"http://localhost:{port}/accounts",
        json={"name": "AC2 Zero Balance", "type": "cash"},
    ).json()

    balance = requests.get(f"http://localhost:{port}/accounts/{account['id']}/balance")
    assert balance.status_code == 200
    assert balance.json()["balance"] == 0


def test_ac4_get_account_by_id(dev_server):
    port = dev_server
    created = requests.post(
        f"http://localhost:{port}/accounts",
        json={"name": "AC4 Wallet", "type": "cash"},
    ).json()

    found = requests.get(f"http://localhost:{port}/accounts/{created['id']}")
    assert found.status_code == 200
    assert found.json()["name"] == "AC4 Wallet"


def test_ac4_get_unknown_account_returns_404(dev_server):
    port = dev_server
    response = requests.get(f"http://localhost:{port}/accounts/999999")
    assert response.status_code == 404


def test_ac5_patch_updates_persist(dev_server):
    port = dev_server
    created = requests.post(
        f"http://localhost:{port}/accounts",
        json={"name": "AC5 Original", "type": "cash"},
    ).json()

    updated = requests.patch(
        f"http://localhost:{port}/accounts/{created['id']}",
        json={"name": "AC5 Renamed", "type": "debit_card"},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "AC5 Renamed"
    assert updated.json()["type"] == "debit_card"

    refetched = requests.get(f"http://localhost:{port}/accounts/{created['id']}")
    assert refetched.json()["name"] == "AC5 Renamed"


def test_ac5_patch_rejects_duplicate_name(dev_server):
    port = dev_server
    a = requests.post(
        f"http://localhost:{port}/accounts",
        json={"name": "AC5 First", "type": "cash"},
    ).json()
    b = requests.post(
        f"http://localhost:{port}/accounts",
        json={"name": "AC5 Second", "type": "cash"},
    ).json()

    response = requests.patch(
        f"http://localhost:{port}/accounts/{b['id']}",
        json={"name": "AC5 First"},
    )
    assert 400 <= response.status_code < 500

    refetched = requests.get(f"http://localhost:{port}/accounts/{b['id']}")
    assert refetched.json()["name"] == "AC5 Second"


def test_ac6_delete_account_then_get_returns_404(dev_server):
    port = dev_server
    created = requests.post(
        f"http://localhost:{port}/accounts",
        json={"name": "AC6 ToDelete", "type": "cash"},
    ).json()

    deleted = requests.delete(f"http://localhost:{port}/accounts/{created['id']}")
    assert deleted.status_code == 204

    refetched = requests.get(f"http://localhost:{port}/accounts/{created['id']}")
    assert refetched.status_code == 404


def test_ui_delete_account_shows_transaction_conflict(dev_server):
    port = dev_server
    account = requests.post(
        f"http://localhost:{port}/accounts",
        json={"name": "UI Protected Account", "type": "cash"},
    ).json()
    transaction = requests.post(
        f"http://localhost:{port}/transactions",
        json={"type": "income", "account_id": account["id"], "amount": 100},
    )
    assert transaction.status_code == 201

    response = requests.post(f"http://localhost:{port}/ui/accounts/{account['id']}/delete")

    assert response.status_code == 200
    assert "Account has transactions" in response.text


def test_ac7_root_returns_dashboard_page(dev_server):
    port = dev_server
    response = requests.get(f"http://localhost:{port}/")
    assert response.status_code == 200
    assert "Money Manager" in response.text
    assert "Dashboard" in response.text
