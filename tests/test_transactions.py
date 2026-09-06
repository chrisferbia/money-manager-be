"""Tests for specs/0003-transactions.md."""

import requests
import pytest


pytestmark = pytest.mark.integration


def create_account(port, name, type_="cash"):
    response = requests.post(
        f"http://localhost:{port}/accounts",
        json={"name": name, "type": type_},
    )
    assert response.status_code == 201
    return response.json()


def create_category(port, name, type_="expense"):
    response = requests.post(
        f"http://localhost:{port}/categories",
        json={"name": name, "type": type_},
    )
    assert response.status_code == 201
    return response.json()


def create_income(port, account_id, amount, occurred_at="2026-08-10T10:00:00Z"):
    return requests.post(
        f"http://localhost:{port}/transactions",
        json={
            "type": "income",
            "account_id": account_id,
            "amount": amount,
            "occurred_at": occurred_at,
        },
    )


def create_expense(port, account_id, category_id, amount, occurred_at="2026-08-10T10:00:00Z"):
    return requests.post(
        f"http://localhost:{port}/transactions",
        json={
            "type": "expense",
            "account_id": account_id,
            "category_id": category_id,
            "amount": amount,
            "occurred_at": occurred_at,
        },
    )


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


def create_transfer_transaction(port, source_account_id, destination_account_id, **overrides):
    payload = {
        "type": "transfer",
        "account_id": source_account_id,
        "related_account_id": destination_account_id,
        "amount": 500,
        "description": "Move money",
        "occurred_at": "2026-08-11T10:00:00Z",
    }
    payload.update(overrides)
    return requests.post(f"http://localhost:{port}/transfers", json=payload)


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


def test_ac1_income_transaction_can_have_category(dev_server):
    port = dev_server
    account = create_account(port, "AC1 Categorized Income")
    category = create_category(port, "AC1 Salary", type_="income")

    response = create_income_transaction(port, account["id"], category_id=category["id"])

    assert response.status_code == 201
    assert response.json()["category_id"] == category["id"]


def test_transaction_category_type_must_match_transaction_type(dev_server):
    port = dev_server
    account = create_account(port, "Category Type Account")
    income_category = create_category(port, "Salary", type_="income")
    expense_category = create_category(port, "Groceries", type_="expense")

    income = create_income_transaction(port, account["id"], category_id=expense_category["id"])
    expense = create_expense_transaction(port, account["id"], income_category["id"])

    assert income.status_code == 400
    assert expense.status_code == 400


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


def test_transaction_counterparty_can_be_created_and_updated(dev_server):
    port = dev_server
    account = create_account(port, "Counterparty Account")
    category = create_category(port, "Counterparty Category")

    created = create_expense_transaction(
        port,
        account["id"],
        category["id"],
        counterparty="Grocery Store",
    )
    assert created.status_code == 201
    transaction = created.json()
    assert transaction["counterparty"] == "Grocery Store"

    updated = requests.patch(
        f"http://localhost:{port}/transactions/{transaction['id']}",
        json={"counterparty": "Buying dinner"},
    )
    assert updated.status_code == 200
    assert updated.json()["counterparty"] == "Buying dinner"


def test_ac3_unknown_account_is_rejected_without_insert(dev_server):
    port = dev_server
    account = create_account(port, "AC3 Cash")

    bad_account = requests.post(
        f"http://localhost:{port}/transactions",
        json={"type": "income", "account_id": 999999, "amount": 100},
    )
    assert bad_account.status_code == 404

    listing = requests.get(f"http://localhost:{port}/transactions")
    assert listing.status_code == 200
    assert listing.json() == []


def test_ac3b_transfer_creation_and_account_filter_includes_destination(dev_server):
    port = dev_server
    source = create_account(port, "Transfer Source")
    destination = create_account(port, "Transfer Destination")

    response = create_transfer_transaction(port, source["id"], destination["id"])
    assert response.status_code == 201
    body = response.json()
    assert body["type"] == "transfer"
    assert body["account_id"] == source["id"]
    assert body["related_account_id"] == destination["id"]
    assert body["category_id"] is None

    by_destination = requests.get(
        f"http://localhost:{port}/transactions", params={"account_id": destination["id"]}
    )
    assert by_destination.status_code == 200
    assert [item["id"] for item in by_destination.json()] == [body["id"]]


def test_ac3c_transfer_rejects_unknown_destination(dev_server):
    port = dev_server
    source = create_account(port, "Transfer Bad Source")

    bad_destination = create_transfer_transaction(port, source["id"], 999999)
    assert bad_destination.status_code == 404


def test_ac3d_transfer_endpoint_rejects_non_transfer_type(dev_server):
    port = dev_server
    source = create_account(port, "Transfer Wrong Type Source")
    destination = create_account(port, "Transfer Wrong Type Destination")

    response = requests.post(
        f"http://localhost:{port}/transfers",
        json={
            "type": "expense",
            "account_id": source["id"],
            "related_account_id": destination["id"],
            "amount": 500,
        },
    )
    assert 400 <= response.status_code < 500


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


def test_ac6_patch_updates_fields_and_can_change_transaction_type(dev_server):
    port = dev_server
    account = create_account(port, "AC6 Cash")
    category = create_category(port, "AC6 Food")
    other_category = create_category(port, "AC6 Transport")
    income_category = create_category(port, "AC6 Salary", type_="income")
    destination = create_account(port, "AC6 Destination")
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

    changed_to_income = requests.patch(
        f"http://localhost:{port}/transactions/{created['id']}",
        json={"type": "income", "category_id": income_category["id"]},
    )
    assert changed_to_income.status_code == 200
    assert changed_to_income.json()["type"] == "income"
    assert changed_to_income.json()["category_id"] == income_category["id"]
    assert changed_to_income.json()["related_account_id"] is None

    changed_to_transfer = requests.patch(
        f"http://localhost:{port}/transactions/{created['id']}",
        json={
            "type": "transfer",
            "category_id": None,
            "related_account_id": destination["id"],
        },
    )
    assert changed_to_transfer.status_code == 200
    assert changed_to_transfer.json()["type"] == "transfer"
    assert changed_to_transfer.json()["category_id"] is None
    assert changed_to_transfer.json()["related_account_id"] == destination["id"]

    changed_to_expense = requests.patch(
        f"http://localhost:{port}/transactions/{created['id']}",
        json={"type": "expense", "category_id": category["id"], "related_account_id": None},
    )
    assert changed_to_expense.status_code == 200
    assert changed_to_expense.json()["type"] == "expense"
    assert changed_to_expense.json()["category_id"] == category["id"]
    assert changed_to_expense.json()["related_account_id"] is None

    reject_account = requests.patch(
        f"http://localhost:{port}/transactions/{created['id']}",
        json={"account_id": 123456},
    )
    assert 400 <= reject_account.status_code < 500


def test_ac5_transfer_patch_rejects_account_changes(dev_server):
    port = dev_server
    source = create_account(port, "Transfer Patch Source")
    destination = create_account(port, "Transfer Patch Destination")
    transfer = create_transfer_transaction(port, source["id"], destination["id"]).json()

    updated = requests.patch(
        f"http://localhost:{port}/transactions/{transfer['id']}",
        json={"amount": 700, "description": "Updated transfer", "occurred_at": "2026-08-14T10:00:00Z"},
    )
    assert updated.status_code == 200
    assert updated.json()["amount"] == 700
    assert updated.json()["description"] == "Updated transfer"

    reject_account = requests.patch(
        f"http://localhost:{port}/transactions/{transfer['id']}",
        json={"account_id": destination["id"]},
    )
    assert 400 <= reject_account.status_code < 500


def test_ac4_transfer_delete_works_like_other_transactions(dev_server):
    port = dev_server
    source = create_account(port, "Transfer Delete Source")
    destination = create_account(port, "Transfer Delete Destination")
    transfer = create_transfer_transaction(port, source["id"], destination["id"]).json()

    deleted = requests.delete(f"http://localhost:{port}/transactions/{transfer['id']}")
    assert deleted.status_code == 204

    refetched = requests.get(f"http://localhost:{port}/transactions/{transfer['id']}")
    assert refetched.status_code == 404


def test_ac8_deleting_account_with_transfer_returns_409(dev_server):
    port = dev_server
    source = create_account(port, "Transfer Account Source")
    destination = create_account(port, "Transfer Account Destination")
    create_transfer_transaction(port, source["id"], destination["id"])

    deleted = requests.delete(f"http://localhost:{port}/accounts/{source['id']}")
    assert deleted.status_code == 409


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


def test_ac1_balance_api_reflects_income_expense_and_transfer(dev_server):
    port = dev_server
    source = create_account(port, "Balance Source")
    destination = create_account(port, "Balance Destination")
    category = create_category(port, "Balance Food")

    assert create_income(port, source["id"], 1000).status_code == 201
    assert create_expense(port, source["id"], category["id"], 200).status_code == 201
    assert create_transfer_transaction(port, source["id"], destination["id"], amount=300).status_code == 201

    source_balance = requests.get(f"http://localhost:{port}/accounts/{source['id']}/balance")
    destination_balance = requests.get(f"http://localhost:{port}/accounts/{destination['id']}/balance")
    assert source_balance.status_code == 200
    assert destination_balance.status_code == 200
    assert source_balance.json()["balance"] == 500
    assert destination_balance.json()["balance"] == 300


def test_ac3_accounts_include_balance_matches_balance_endpoint(dev_server):
    port = dev_server
    account = create_account(port, "List Balance Account")
    category = create_category(port, "List Balance Category")
    assert create_income(port, account["id"], 700).status_code == 201
    assert create_expense(port, account["id"], category["id"], 250).status_code == 201

    list_response = requests.get(f"http://localhost:{port}/accounts", params={"include_balance": "true"})
    balance_response = requests.get(f"http://localhost:{port}/accounts/{account['id']}/balance")
    assert list_response.status_code == 200
    assert balance_response.status_code == 200
    row = next(item for item in list_response.json() if item["id"] == account["id"])
    assert row["balance"] == balance_response.json()["balance"]


def test_ac4_expenses_by_category_filters_and_omits_empty_categories(dev_server):
    port = dev_server
    account = create_account(port, "Report Account", type_="debit_card")
    food = create_category(port, "Report Food")
    travel = create_category(port, "Report Travel")
    create_category(port, "Report Empty")

    assert create_expense(port, account["id"], food["id"], 200, occurred_at="2026-08-10T10:00:00Z").status_code == 201
    assert create_expense(port, account["id"], food["id"], 300, occurred_at="2026-08-12T10:00:00Z").status_code == 201
    assert create_expense(port, account["id"], travel["id"], 400, occurred_at="2026-08-11T10:00:00Z").status_code == 201

    report = requests.get(f"http://localhost:{port}/reports/expenses-by-category")
    assert report.status_code == 200
    totals = {row["name"]: row["total"] for row in report.json()}
    assert totals == {"Report Food": 500, "Report Travel": 400}
    assert "Report Empty" not in totals

    ranged = requests.get(
        f"http://localhost:{port}/reports/expenses-by-category",
        params={"from": "2026-08-11T00:00:00Z", "to": "2026-08-11T23:59:59Z"},
    )
    ranged_totals = {row["name"]: row["total"] for row in ranged.json()}
    assert ranged_totals == {"Report Travel": 400}


def test_ac6_ui_balance_and_report_pages_render(dev_server):
    port = dev_server
    account = create_account(port, "UI Balance Account")
    category = create_category(port, "UI Report Category")
    assert create_income(port, account["id"], 900).status_code == 201
    assert create_expense(port, account["id"], category["id"], 100).status_code == 201

    accounts_page = requests.get(f"http://localhost:{port}/ui/accounts")
    report_page = requests.get(f"http://localhost:{port}/ui/reports/expenses-by-category")
    assert accounts_page.status_code == 200
    assert report_page.status_code == 200
    assert "800" in accounts_page.text
    assert "UI Report Category" in report_page.text


def test_transaction_form_has_type_specific_account_and_category_controls(dev_server):
    port = dev_server
    create_category(port, "UI Salary Category", type_="income")
    create_category(port, "UI Food Category", type_="expense")

    page = requests.get(f"http://localhost:{port}/ui/transactions")

    assert page.status_code == 200
    assert 'id="destination-account-field"' in page.text
    assert 'id="category-field"' in page.text
    assert 'data-category-type="income"' in page.text
    assert 'data-category-type="expense"' in page.text
    assert 'transactionType.value === "transfer"' in page.text


def test_ac5_expenses_by_category_date_filter_is_inclusive(dev_server):
    port = dev_server
    account = create_account(port, "Report Inclusive", type_="debit_card")
    category = create_category(port, "Report Inclusive Category")

    assert create_expense(port, account["id"], category["id"], 100, occurred_at="2026-08-11T00:00:00Z").status_code == 201
    assert create_expense(port, account["id"], category["id"], 200, occurred_at="2026-08-11T23:59:59Z").status_code == 201

    report = requests.get(
        f"http://localhost:{port}/reports/expenses-by-category",
        params={"from": "2026-08-11T00:00:00Z", "to": "2026-08-11T23:59:59Z"},
    )
    assert report.status_code == 200
    totals = {row["name"]: row["total"] for row in report.json()}
    assert totals == {"Report Inclusive Category": 300}


def test_ac7_ui_balance_page_shows_zero_for_empty_account(dev_server):
    port = dev_server
    account = create_account(port, "UI Empty Account")

    page = requests.get(f"http://localhost:{port}/ui/accounts")
    assert page.status_code == 200
    assert account["name"] in page.text
    assert ">0<" in page.text or " 0 " in page.text


def test_dashboard_date_range_limits_period_summary_and_report(dev_server):
    port = dev_server
    account = create_account(port, "Dashboard Range Account")
    category = create_category(port, "Dashboard Range Category")

    assert create_income(
        port, account["id"], 1000, occurred_at="2026-08-01T10:00:00Z"
    ).status_code == 201
    assert create_expense(
        port,
        account["id"],
        category["id"],
        250,
        occurred_at="2026-08-15T10:00:00Z",
    ).status_code == 201
    assert create_expense(
        port,
        account["id"],
        category["id"],
        900,
        occurred_at="2026-08-31T23:59:59Z",
    ).status_code == 201

    page = requests.get(
        f"http://localhost:{port}/",
        params={"from": "2026-08-01", "to": "2026-08-15"},
    )

    assert page.status_code == 200
    assert "Period income" in page.text
    assert ">1000<" in page.text
    assert ">250<" in page.text
    assert ">750<" in page.text
    assert ">900<" not in page.text
