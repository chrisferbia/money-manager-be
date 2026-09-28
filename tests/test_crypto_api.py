import pytest
import requests

import crypto


pytestmark = pytest.mark.integration


def account(name, mode="ledger"):
    response = requests.post("http://localhost/accounts", json={
        "name": name, "type": "investment", "valuation_mode": mode,
    })
    assert response.status_code == 201
    return response.json()


def holding(account_id, coin_id="bitcoin", quantity="0.01"):
    return requests.post(f"http://localhost/accounts/{account_id}/holdings", json={
        "coin_id": coin_id, "name": "Bitcoin", "symbol": "BTC", "quantity": quantity,
    })


def test_crypto_market_value_replaces_ledger_balance(dev_server, monkeypatch):
    async def market(path, env):
        assert "vs_currencies=idr" in path
        return {"bitcoin": {"idr": 1_500_000_000, "last_updated_at": 1_780_000_000}}

    monkeypatch.setattr(crypto, "_fetch_market_json", market)
    investment = account("Existing investment")
    cash = requests.post("http://localhost/accounts", json={"name": "Cash", "type": "cash"}).json()
    requests.post("http://localhost/transactions", json={
        "type": "income", "account_id": investment["id"], "amount": 10_000_000,
    })
    requests.post("http://localhost/transactions", json={
        "type": "income", "account_id": cash["id"], "amount": 20_000_000,
    })
    rejected = requests.patch(f"http://localhost/accounts/{investment['id']}", json={"valuation_mode": "crypto"})
    assert rejected.status_code == 409
    enabled = requests.patch(f"http://localhost/accounts/{investment['id']}", json={
        "valuation_mode": "crypto", "confirm_ledger_replacement": True,
    })
    assert enabled.status_code == 200
    added = holding(investment["id"])
    assert added.status_code == 201
    assert added.json()["value_idr"] == 15_000_000
    rows = requests.get("http://localhost/accounts", params={"include_balance": "true"}).json()
    assert next(row for row in rows if row["id"] == investment["id"])["balance"] == 15_000_000
    assert next(row for row in rows if row["id"] == cash["id"])["balance"] == 20_000_000
    assert sum(row["balance"] or 0 for row in rows) == 35_000_000


def test_holdings_validation_edit_delete_and_missing_price(dev_server, monkeypatch):
    async def unavailable(path, env):
        raise RuntimeError("offline")

    monkeypatch.setattr(crypto, "_fetch_market_json", unavailable)
    first = account("Crypto 1", "crypto")
    second = account("Crypto 2", "crypto")
    assert holding(first["id"], quantity="0").status_code == 400
    added = holding(first["id"], quantity="0.00000001")
    assert added.status_code == 201
    assert added.json()["price_status"] == "unavailable"
    assert added.json()["value_idr"] is None
    assert holding(first["id"]).status_code == 409
    assert requests.get("http://localhost/accounts", params={"include_balance": "true"}).json()[0]["balance"] is None
    holding_id = added.json()["id"]
    wrong_account = requests.patch(f"http://localhost/accounts/{second['id']}/holdings/{holding_id}", json={"quantity": "2"})
    assert wrong_account.status_code == 404
    changed = requests.patch(f"http://localhost/accounts/{first['id']}/holdings/{holding_id}", json={"quantity": "1.5000"})
    assert changed.json()["quantity"] == "1.5"
    assert requests.delete(f"http://localhost/accounts/{first['id']}/holdings/{holding_id}").status_code == 204
    assert requests.get(f"http://localhost/accounts/{first['id']}/balance").json()["balance"] == 0


def test_crypto_requires_investment_and_protects_holdings(dev_server, monkeypatch):
    async def market(path, env):
        return {"bitcoin": {"idr": 1000}}

    monkeypatch.setattr(crypto, "_fetch_market_json", market)
    invalid = requests.post("http://localhost/accounts", json={
        "name": "Not investment", "type": "cash", "valuation_mode": "crypto",
    })
    assert invalid.status_code == 400
    investment = account("Protected", "crypto")
    assert holding(investment["id"]).status_code == 201
    assert requests.post("http://localhost/transactions", json={
        "type": "income", "account_id": investment["id"], "amount": 100,
    }).status_code == 400
    assert requests.delete(f"http://localhost/accounts/{investment['id']}").status_code == 409
    assert requests.patch(f"http://localhost/accounts/{investment['id']}", json={
        "valuation_mode": "ledger",
    }).status_code == 409


def test_failed_refresh_uses_stale_price_without_hiding_its_age(dev_server, inprocess_app, monkeypatch):
    async def market(path, env):
        return {"bitcoin": {"idr": 200_000}}

    monkeypatch.setattr(crypto, "_fetch_market_json", market)
    investment = account("Stale quote", "crypto")
    assert holding(investment["id"], quantity="2").status_code == 201
    database, _ = inprocess_app
    database.connection.execute("UPDATE crypto_prices SET fetched_at = '2020-01-01T00:00:00Z'")
    database.connection.commit()

    async def unavailable(path, env):
        raise RuntimeError("rate limited")

    monkeypatch.setattr(crypto, "_fetch_market_json", unavailable)
    holdings = requests.get(f"http://localhost/accounts/{investment['id']}/holdings").json()
    assert holdings[0]["price_status"] == "stale"
    assert holdings[0]["value_idr"] == 400_000
    assert requests.get(f"http://localhost/accounts/{investment['id']}/balance").json()["balance"] == 400_000
