from datetime import datetime, timedelta, timezone

import pytest
import crypto

pytestmark = pytest.mark.integration
SETTINGS = "/settings/crypto-prices"


def setup(client):
    account = client.post("/accounts", json={"name": "Fictional crypto", "type": "investment", "valuation_mode": "crypto"}).json()
    return account["id"]


def add(client, account_id, coin="bitcoin"):
    return client.post(f"/accounts/{account_id}/holdings", json={"coin_id": coin, "name": coin.title(), "symbol": coin[:3], "quantity": "2"})


def test_settings_default_validation_and_workspace_isolation(inprocess_app):
    database, client = inprocess_app
    database.connection.execute("INSERT INTO workspaces (id,name) VALUES (2,'Fictional second user')")
    database.connection.commit()
    assert client.get(SETTINGS).json() == {"expiry_minutes": 10}
    assert client.patch(SETTINGS, json={"expiry_minutes": 1}).json() == {"expiry_minutes": 1}
    assert client.get(SETTINGS, headers={"X-Test-Workspace": "2"}).json() == {"expiry_minutes": 10}
    assert client.patch(SETTINGS, headers={"X-Test-Workspace": "2"}, json={"expiry_minutes": 1440}).status_code == 200
    assert client.get(SETTINGS).json() == {"expiry_minutes": 1}
    for payload in ({}, {"expiry_minutes": 0}, {"expiry_minutes": 1441}, {"expiry_minutes": 1.5}, {"expiry_minutes": True}, {"expiry_minutes": "10"}, {"expiry_minutes": None}, {"expiry_minutes": 10, "workspace_id": 2}):
        assert client.patch(SETTINGS, json=payload).status_code == 422
    assert client.get(SETTINGS).json() == {"expiry_minutes": 1}


def test_new_expiry_controls_cache_reuse_and_stale_status(inprocess_app, monkeypatch):
    database, client = inprocess_app
    calls = []
    async def market(path, env):
        calls.append(path)
        return {"bitcoin": {"idr": 200000}}
    monkeypatch.setattr(crypto, "_fetch_market_json", market)
    account_id = setup(client)
    assert add(client, account_id).status_code == 201
    old_time = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    database.connection.execute("UPDATE crypto_prices SET fetched_at = ?", (old_time,))
    database.connection.commit()
    calls.clear()
    assert client.get(f"/accounts/{account_id}/holdings").json()[0]["price_status"] == "fresh"
    assert calls == []
    client.patch(SETTINGS, json={"expiry_minutes": 2})
    assert client.get(f"/accounts/{account_id}/holdings").json()[0]["price_status"] == "fresh"
    assert len(calls) == 1
    database.connection.execute("UPDATE crypto_prices SET fetched_at = ?", (old_time,))
    database.connection.commit()
    async def offline(path, env):
        raise RuntimeError("offline")
    monkeypatch.setattr(crypto, "_fetch_market_json", offline)
    stale = client.get(f"/accounts/{account_id}/holdings").json()[0]
    assert stale["price_status"] == "stale"
    assert stale["fetched_at"] == old_time
    assert stale["value_idr"] == 400000


def test_manual_refresh_bypasses_fresh_cache_and_updates_balance(inprocess_app, monkeypatch):
    _, client = inprocess_app
    price, calls = 1000, []
    async def market(path, env):
        calls.append(path)
        return {"bitcoin": {"idr": price}}
    monkeypatch.setattr(crypto, "_fetch_market_json", market)
    account_id = setup(client)
    add(client, account_id)
    calls.clear()
    price = 2500
    assert client.get(f"/accounts/{account_id}/holdings").json()[0]["price_idr"] == "1000"
    assert calls == []
    result = client.post(f"/accounts/{account_id}/holdings/refresh-prices")
    assert result.status_code == 200
    assert len(calls) == 1
    assert result.json()["refreshed_count"] == result.json()["requested_count"] == 1
    assert result.json()["failed_coin_ids"] == []
    assert result.json()["holdings"][0]["value_idr"] == 5000
    assert client.get(f"/accounts/{account_id}/balance").json()["balance"] == 5000
    assert client.get("/transactions").json() == []


@pytest.mark.parametrize("provider_result", [None, {}, {"bitcoin": {"idr": -1}}, {"bitcoin": {"idr": 2000, "last_updated_at": 10**30}}])
def test_manual_failure_does_not_mark_old_price_fresh(inprocess_app, monkeypatch, provider_result):
    database, client = inprocess_app
    async def initial(path, env):
        return {"bitcoin": {"idr": 1000}}
    monkeypatch.setattr(crypto, "_fetch_market_json", initial)
    account_id = setup(client)
    add(client, account_id)
    before = tuple(database.connection.execute("SELECT * FROM crypto_prices").fetchone())
    async def failed(path, env):
        if provider_result is None:
            raise RuntimeError("rate limited")
        return provider_result
    monkeypatch.setattr(crypto, "_fetch_market_json", failed)
    response = client.post(f"/accounts/{account_id}/holdings/refresh-prices")
    assert response.status_code == 503
    assert "Last known prices were kept" in response.json()["detail"]
    assert tuple(database.connection.execute("SELECT * FROM crypto_prices").fetchone()) == before


def test_manual_partial_refresh_reports_missing_coins(inprocess_app, monkeypatch):
    database, client = inprocess_app
    async def initial(path, env):
        return {"bitcoin": {"idr": 1000}, "ethereum": {"idr": 500}}
    monkeypatch.setattr(crypto, "_fetch_market_json", initial)
    account_id = setup(client)
    add(client, account_id)
    add(client, account_id, "ethereum")
    old_eth = tuple(database.connection.execute("SELECT * FROM crypto_prices WHERE coin_id = 'ethereum'").fetchone())
    async def partial(path, env):
        return {"bitcoin": {"idr": 1500}}
    monkeypatch.setattr(crypto, "_fetch_market_json", partial)
    result = client.post(f"/accounts/{account_id}/holdings/refresh-prices").json()
    assert result["refreshed_count"] == 1
    assert result["requested_count"] == 2
    assert result["failed_coin_ids"] == ["ethereum"]
    assert tuple(database.connection.execute("SELECT * FROM crypto_prices WHERE coin_id = 'ethereum'").fetchone()) == old_eth


def test_manual_refresh_rejects_foreign_accounts_and_ledger_accounts(inprocess_app, monkeypatch):
    database, client = inprocess_app
    database.connection.execute("INSERT INTO workspaces (id,name) VALUES (2,'Fictional second user')")
    database.connection.commit()
    account_id = setup(client)
    async def must_not_fetch(path, env):
        pytest.fail("Unauthorized/empty refresh must not contact the provider")
    monkeypatch.setattr(crypto, "_fetch_market_json", must_not_fetch)
    assert client.post(f"/accounts/{account_id}/holdings/refresh-prices", headers={"X-Test-Workspace": "2"}).status_code == 404
    assert client.post(f"/accounts/{account_id}/holdings/refresh-prices").json()["requested_count"] == 0
    ledger = client.post("/accounts", json={"name": "Fictional bank", "type": "bank"}).json()["id"]
    assert client.post(f"/accounts/{ledger}/holdings/refresh-prices").status_code == 400


def test_authentication_required_and_demo_cannot_mutate_settings_or_refresh(inprocess_app):
    from app import app
    from auth import require_subject, require_workspace
    from fastapi import HTTPException
    database, client = inprocess_app
    before = tuple(database.connection.iterdump())
    override = app.dependency_overrides.pop(require_workspace)
    def signed_out():
        raise HTTPException(401, "Sign-in required")
    app.dependency_overrides[require_subject] = signed_out
    try:
        assert client.get(SETTINGS).status_code == 401
        assert client.patch(SETTINGS, json={"expiry_minutes": 1}).status_code == 401
        assert client.post("/accounts/1/holdings/refresh-prices").status_code == 401
        assert client.patch("/demo/settings/crypto-prices", json={"expiry_minutes": 1}).status_code == 404
        assert client.post("/demo/accounts/1/holdings/refresh-prices").status_code == 404
        assert tuple(database.connection.iterdump()) == before
    finally:
        app.dependency_overrides[require_workspace] = override
        app.dependency_overrides.pop(require_subject, None)
