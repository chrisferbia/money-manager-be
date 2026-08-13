"""Tests for specs/0003-transactions.md."""

import requests


def create_account(port, name, type_="cash"):
    response = requests.post(
        f"http://localhost:{port}/accounts",
        json={"name": name, "type": type_},
    )
    assert response.status_code == 201
    return response.json()


def create_category(port, name):
    response = requests.post(
        f"http://localhost:{port}/categories",
        json={"name": name},
    )
    assert response.status_code == 201
    return response.json()


def create_income_transaction(port, account_id, **overrides):
    payload = {
        "type": "income",
        "account_id": account_id,
        "amount": 1000,
        "description": "Salary",
        "occurred_at": "2026-08-10T10:00:00Z",
    }
    payload.update(overrides)
    return requests.post(f"http://localhost:{port}/transactions", json=payload)


def create_expense_transaction(port, account_id, category_id, **overrides):
    payload = {
        "type": "expense",
        "account_id": account_id,
        "category_id": category_id,
        "amount": 250,
        "description": "Groceries",
        "occurred_at": "2026-08-11T10:00:00Z",
    }
    payload.update(overrides)
    return requests.post(f"http://localhost:{port}/transactions", json=payload)


def test_ac1_create_income_transaction_returns_201(dev_server):
    port = dev_server
    account = create_account(port, "AC1 Cash")

    response = create_income_transaction(port, account["id"], category_id=None)
    assert response.status_code == 201
    body = response.json()
    assert body["type"] == "income"
    assert body["account_id"] == account["id"]
    assert body["category_id"] is None
    assert body["amount"] == 1000
    assert isinstance(body["id"], int)


def test_ac2_create_expense_transaction_returns_201(dev_server):
    port = dev_server
    account = create_account(port, "AC2 Debit", type_="debit_card")
    category = create_category(port, "AC2 Groceries")

    response = create_expense_transaction(port, account["id"], category["id"])
    assert response.status_code == 201
    body = response.json()
    assert body["type"] == "expense"
    assert body["account_id"] == account["id"]
    assert body["category_id"] == category["id"]
    assert body["amount"] == 250
    assert isinstance(body["id"], int)


def test_ac3_invalid_transaction_payloads_are_rejected(dev_server):
    port = dev_server
    account = create_account(port, "AC3 Cash")
    category = create_category(port, "AC3 Food")

    missing_category = requests.post(
        f"http://localhost:{port}/transactions",
        json={"type": "expense", "account_id": account["id"], "amount": 100},
    )
    assert 400 <= missing_category.status_code < 500

    income_with_category = requests.post(
        f"http://localhost:{port}/transactions",
        json={
            "type": "income",
            "account_id": account["id"],
            "category_id": category["id"],
            "amount": 100,
        },
    )
    assert 400 <= income_with_category.status_code < 500

    zero_amount = requests.post(
        f"http://localhost:{port}/transactions",
        json={"type": "income", "account_id": account["id"], "amount": 0},
    )
    assert 400 <= zero_amount.status_code < 500

    bad_account = requests.post(
        f"http://localhost:{port}/transactions",
        json={"type": "income", "account_id": 999999, "amount": 100},
    )
    assert 400 <= bad_account.status_code < 500

    bad_category = requests.post(
        f"http://localhost:{port}/transactions",
        json={
            "type": "expense",
            "account_id": account["id"],
            "category_id": 999999,
            "amount": 100,
        },
    )
    assert 400 <= bad_category.status_code < 500

    listing = requests.get(f"http://localhost:{port}/transactions")
    assert listing.status_code == 200
    assert listing.json() == []


def test_ac4_list_transactions_filters_and_orders_newest_first(dev_server):
    port = dev_server
    account_a = create_account(port, "AC4 Cash")
    account_b = create_account(port, "AC4 Debit", type_="debit_card")
    category_food = create_category(port, "AC4 Food")
    category_transport = create_category(port, "AC4 Transport")

    old_income = create_income_transaction(
        port,
        account_a["id"],
        amount=100,
        occurred_at="2026-08-10T10:00:00Z",
    ).json()
    food_expense = create_expense_transaction(
        port,
        account_a["id"],
        category_food["id"],
        amount=200,
        occurred_at="2026-08-12T10:00:00Z",
    ).json()
    account_b_income = create_income_transaction(
        port,
        account_b["id"],
        amount=300,
        occurred_at="2026-08-11T10:00:00Z",
    ).json()
    transport_expense = create_expense_transaction(
        port,
        account_b["id"],
        category_transport["id"],
        amount=400,
        occurred_at="2026-08-13T10:00:00Z",
    ).json()

    by_account = requests.get(f"http://localhost:{port}/transactions", params={"account_id": account_a["id"]})
    assert by_account.status_code == 200
    by_account_ids = [item["id"] for item in by_account.json()]
    assert by_account_ids == [food_expense["id"], old_income["id"]]

    by_category = requests.get(
        f"http://localhost:{port}/transactions",
        params={"category_id": category_food["id"]},
    )
    assert [item["id"] for item in by_category.json()] == [food_expense["id"]]

    by_type = requests.get(f"http://localhost:{port}/transactions", params={"type": "expense"})
    assert [item["id"] for item in by_type.json()] == [transport_expense["id"], food_expense["id"]]

    by_range = requests.get(
        f"http://localhost:{port}/transactions",
        params={"from": "2026-08-11T00:00:00Z", "to": "2026-08-12T23:59:59Z"},
    )
    assert [item["id"] for item in by_range.json()] == [food_expense["id"], account_b_income["id"]]


def test_ac5_get_transaction_by_id_and_404(dev_server):
    port = dev_server
    account = create_account(port, "AC5 Cash")
    created = create_income_transaction(port, account["id"]).json()

    found = requests.get(f"http://localhost:{port}/transactions/{created['id']}")
    assert found.status_code == 200
    assert found.json()["id"] == created["id"]

    missing = requests.get(f"http://localhost:{port}/transactions/999999")
    assert missing.status_code == 404


def test_ac6_patch_updates_allowed_fields_and_rejects_type_or_account_changes(dev_server):
    port = dev_server
    account = create_account(port, "AC6 Cash")
    category = create_category(port, "AC6 Food")
    other_category = create_category(port, "AC6 Transport")
    created = create_expense_transaction(port, account["id"], category["id"]).json()

    updated = requests.patch(
        f"http://localhost:{port}/transactions/{created['id']}",
        json={
            "amount": 999,
            "category_id": other_category["id"],
            "description": "Updated",
            "occurred_at": "2026-08-14T10:00:00Z",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["amount"] == 999
    assert updated.json()["category_id"] == other_category["id"]
    assert updated.json()["description"] == "Updated"

    reject_type = requests.patch(
        f"http://localhost:{port}/transactions/{created['id']}",
        json={"type": "income"},
    )
    assert 400 <= reject_type.status_code < 500

    reject_account = requests.patch(
        f"http://localhost:{port}/transactions/{created['id']}",
        json={"account_id": 123456},
    )
    assert 400 <= reject_account.status_code < 500


def test_ac7_delete_transaction_then_get_returns_404(dev_server):
    port = dev_server
    account = create_account(port, "AC7 Cash")
    created = create_income_transaction(port, account["id"]).json()

    deleted = requests.delete(f"http://localhost:{port}/transactions/{created['id']}")
    assert deleted.status_code == 204

    refetched = requests.get(f"http://localhost:{port}/transactions/{created['id']}")
    assert refetched.status_code == 404


def test_ac8_deleting_account_with_transactions_returns_409(dev_server):
    port = dev_server
    account = create_account(port, "AC8 Cash")
    create_income_transaction(port, account["id"])

    deleted = requests.delete(f"http://localhost:{port}/accounts/{account['id']}")
    assert deleted.status_code == 409

    refetched = requests.get(f"http://localhost:{port}/accounts/{account['id']}")
    assert refetched.status_code == 200


def test_ac9_deleting_category_with_expense_transaction_returns_409(dev_server):
    port = dev_server
    account = create_account(port, "AC9 Debit", type_="debit_card")
    category = create_category(port, "AC9 Food")
    create_expense_transaction(port, account["id"], category["id"])

    deleted = requests.delete(f"http://localhost:{port}/categories/{category['id']}")
    assert deleted.status_code == 409

    refetched = requests.get(f"http://localhost:{port}/categories/{category['id']}")
    assert refetched.status_code == 200
