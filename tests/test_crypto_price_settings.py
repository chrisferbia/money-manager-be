from datetime import datetime, timedelta, timezone
import logging
from urllib.parse import parse_qs, urlsplit

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
    assert client.get(f"/accounts/{account_id}/holdings").json()[0]["price_idr"] == "2500"
    assert client.get("/accounts?include_balance=true").status_code == 200
    assert len(calls) == 1  # Follow-up UI reads must not fetch a second quote.
    assert client.get("/transactions").json() == []


def test_fresh_prices_are_reused_across_reads_edits_and_settings_changes(inprocess_app, monkeypatch):
    database, client = inprocess_app
    calls = []
    async def market(path, env):
        calls.append(path)
        return {"bitcoin": {"idr": 1000}}
    monkeypatch.setattr(crypto, "_fetch_market_json", market)
    account_id = setup(client)
    holding = add(client, account_id).json()
    assert len(calls) == 1  # Initial fetch for a coin without a cached quote.
    before = tuple(database.connection.execute("SELECT * FROM crypto_prices").fetchone())
    calls.clear()
    for _ in range(3):
        assert client.get("/accounts?include_balance=true").status_code == 200
        assert client.get(f"/accounts/{account_id}/balance").status_code == 200
        assert client.get(f"/accounts/{account_id}/holdings").status_code == 200
    assert client.patch(SETTINGS, json={"expiry_minutes": 30}).status_code == 200
    assert client.get(SETTINGS).json() == {"expiry_minutes": 30}
    assert client.patch(f"/accounts/{account_id}/holdings/{holding['id']}", json={"quantity": "3"}).status_code == 200
    second_id = client.post("/accounts", json={"name": "Second fictional crypto", "type": "investment", "valuation_mode": "crypto"}).json()["id"]
    assert add(client, second_id).status_code == 201
    # Even adding the same coin to another account uses its existing fresh quote.
    assert client.get("/accounts?include_balance=true").status_code == 200
    assert calls == []
    assert tuple(database.connection.execute("SELECT * FROM crypto_prices").fetchone()) == before


@pytest.mark.parametrize("read_path", [
    "/accounts?include_balance=true",
    "/accounts/{account_id}/balance",
    "/accounts/{account_id}/holdings",
])
def test_automatic_fetch_only_at_expiry_and_only_for_expired_coins(inprocess_app, monkeypatch, read_path):
    database, client = inprocess_app
    clock = [datetime(2026, 10, 5, 0, 0, tzinfo=timezone.utc)]
    class FixedClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock[0]
    monkeypatch.setattr(crypto, "datetime", FixedClock)
    calls = []
    async def market(path, env):
        ids = parse_qs(urlsplit(path).query)["ids"][0].split(",")
        calls.append(ids)
        return {coin: {"idr": 2000} for coin in ids}
    monkeypatch.setattr(crypto, "_fetch_market_json", market)
    account_id = setup(client)
    assert add(client, account_id).status_code == 201
    assert add(client, account_id, "ethereum").status_code == 201
    database.connection.execute(
        "UPDATE crypto_prices SET fetched_at = ? WHERE coin_id = 'bitcoin'",
        ((clock[0] - timedelta(seconds=599)).isoformat(),),
    )
    database.connection.commit()
    calls.clear()
    path = read_path.format(account_id=account_id)
    assert client.get(path).status_code == 200
    assert calls == []  # 9m59s old is still fresh with the 10-minute default.
    clock[0] += timedelta(seconds=1)
    assert client.get(path).status_code == 200
    assert calls == [["bitcoin"]]  # Exactly at expiry; ETH is still fresh.
    assert client.get(path).status_code == 200
    assert calls == [["bitcoin"]]  # The newly cached quote is reused.


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
    second_id = client.post("/accounts", json={"name": "Second fictional wallet", "type": "investment", "valuation_mode": "crypto"}).json()["id"]
    add(client, second_id, "ethereum")
    old_eth = tuple(database.connection.execute("SELECT * FROM crypto_prices WHERE coin_id = 'ethereum'").fetchone())
    async def partial(path, env):
        return {"bitcoin": {"idr": 1500}}
    monkeypatch.setattr(crypto, "_fetch_market_json", partial)
    result = client.post(f"/accounts/{account_id}/holdings/refresh-prices").json()
    assert result["refreshed_count"] == 1
    assert result["requested_count"] == 2
    assert result["failed_coin_ids"] == ["ethereum"]
    assert result["holdings_by_account"][str(second_id)][0]["price_idr"] == "500"
    assert tuple(database.connection.execute("SELECT * FROM crypto_prices WHERE coin_id = 'ethereum'").fetchone()) == old_eth


def test_manual_refresh_batches_all_workspace_coins_once_and_excludes_other_users(inprocess_app, monkeypatch):
    database, client = inprocess_app
    calls = []
    price = 1000
    async def market(path, env):
        ids = parse_qs(urlsplit(path).query)["ids"][0].split(",")
        calls.append(ids)
        return {coin: {"idr": price} for coin in ids}
    monkeypatch.setattr(crypto, "_fetch_market_json", market)
    first = setup(client)
    second = client.post("/accounts", json={"name": "Second fictional wallet", "type": "investment", "valuation_mode": "crypto"}).json()["id"]
    empty = client.post("/accounts", json={"name": "Empty fictional wallet", "type": "investment", "valuation_mode": "crypto"}).json()["id"]
    assert add(client, first).status_code == 201
    assert add(client, second).status_code == 201
    assert add(client, second, "ethereum").status_code == 201
    database.connection.executescript("""
        INSERT INTO workspaces (id,name) VALUES (2,'Fictional other user');
        INSERT INTO accounts (id,workspace_id,name,type,valuation_mode) VALUES (99,2,'Other user wallet','investment','crypto');
        INSERT INTO crypto_holdings (workspace_id,account_id,coin_id,name,symbol,quantity) VALUES (2,99,'solana','Solana','SOL','1');
        INSERT INTO crypto_prices (coin_id,price_idr,fetched_at) VALUES ('solana','555','2020-01-01T00:00:00Z');
        INSERT INTO crypto_prices (coin_id,price_idr,fetched_at) VALUES ('unused-coin','777','2020-01-01T00:00:00Z');
    """)
    untouched = list(database.connection.execute("SELECT * FROM crypto_prices WHERE coin_id IN ('solana','unused-coin')"))
    quantities = list(database.connection.execute("SELECT id,quantity FROM crypto_holdings"))
    calls.clear()
    price = 2500
    # Even an empty selected wallet refreshes every coin required by this user.
    response = client.post(f"/accounts/{empty}/holdings/refresh-prices")
    assert response.status_code == 200
    result = response.json()
    assert calls == [["bitcoin", "ethereum"]]
    assert result["requested_count"] == result["refreshed_count"] == 2
    assert result["holdings"] == []
    assert set(result["holdings_by_account"]) == {str(first), str(second), str(empty)}
    assert all(row["price_idr"] == "2500" for rows in result["holdings_by_account"].values() for row in rows)
    assert list(database.connection.execute("SELECT * FROM crypto_prices WHERE coin_id IN ('solana','unused-coin')")) == untouched
    assert list(database.connection.execute("SELECT id,quantity FROM crypto_holdings")) == quantities
    balances = {row["id"]: row["balance"] for row in client.get("/accounts?include_balance=true").json()}
    assert balances[first] == 5000
    assert balances[second] == 10000
    assert client.get(f"/accounts/{first}/holdings").status_code == 200
    assert client.get(f"/accounts/{second}/holdings").status_code == 200
    assert calls == [["bitcoin", "ethereum"]]  # Reads still honor expiry.


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


@pytest.mark.parametrize("manual", [False, True])
@pytest.mark.parametrize("failure, diagnostic", [
    (crypto.MarketProviderError("http_error", 429), "http_status=429"),
    (crypto.MarketProviderError("http_error", 401, 10010), "provider_code=10010"),
    (crypto.MarketProviderError("invalid_json", 200), "reason=invalid_json"),
    (RuntimeError("secret-key private-held-coin quantity=2 user@example.invalid"), "exception_type=RuntimeError"),
])
def test_failed_refresh_logs_safe_diagnostics_and_keeps_cached_quotes(inprocess_app, monkeypatch, caplog, manual, failure, diagnostic):
    database, client = inprocess_app
    async def initial(path, env):
        return {"bitcoin": {"idr": 1000}}
    monkeypatch.setattr(crypto, "_fetch_market_json", initial)
    account_id = setup(client)
    assert add(client, account_id).status_code == 201
    database.connection.execute("UPDATE crypto_prices SET fetched_at = '2020-01-01T00:00:00Z'")
    database.connection.commit()
    before = tuple(database.connection.execute("SELECT * FROM crypto_prices").fetchone())
    async def fail(path, env):
        raise failure
    monkeypatch.setattr(crypto, "_fetch_market_json", fail)
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="crypto"):
        response = client.post(f"/accounts/{account_id}/holdings/refresh-prices") if manual else client.get(f"/accounts/{account_id}/holdings")
    assert response.status_code == (503 if manual else 200)
    records = [record for record in caplog.records if record.name == "crypto"]
    assert len(records) == 1
    message = records[0].getMessage()
    assert diagnostic in message
    assert f"mode={'manual' if manual else 'automatic'}" in message
    assert "api_key_configured=False" in message
    assert "cached prices kept" in message
    assert records[0].exc_info is None
    for sensitive in ("secret-key", "private-held-coin", "bitcoin", "quantity=2", "user@example.invalid", "workspace_id", "account_id"):
        assert sensitive not in message
    assert tuple(database.connection.execute("SELECT * FROM crypto_prices").fetchone()) == before


@pytest.mark.parametrize("quote, reason", [
    ({}, "missing_quote"),
    ([], "invalid_response_shape"),
    ({"bitcoin": "secret-key"}, "invalid_quote_shape"),
    ({"bitcoin": {"idr": "secret-key"}}, "invalid_idr_price"),
    ({"bitcoin": {"idr": 0}}, "invalid_idr_price"),
    ({"bitcoin": {"idr": 2000, "last_updated_at": 10**30}}, "invalid_provider_timestamp"),
])
def test_unusable_quotes_log_only_rejection_reason(inprocess_app, monkeypatch, caplog, quote, reason):
    database, client = inprocess_app
    async def initial(path, env):
        return {"bitcoin": {"idr": 1000}}
    monkeypatch.setattr(crypto, "_fetch_market_json", initial)
    account_id = setup(client)
    add(client, account_id)
    before = tuple(database.connection.execute("SELECT * FROM crypto_prices").fetchone())
    async def invalid(path, env):
        return quote
    monkeypatch.setattr(crypto, "_fetch_market_json", invalid)
    with caplog.at_level(logging.WARNING, logger="crypto"):
        assert client.post(f"/accounts/{account_id}/holdings/refresh-prices").status_code == 503
    assert f"reason={reason}" in caplog.text
    assert "bitcoin" not in caplog.text
    assert "secret-key" not in caplog.text
    assert tuple(database.connection.execute("SELECT * FROM crypto_prices").fetchone()) == before


def test_partial_quote_failure_logs_once_without_disclosing_failed_coin(inprocess_app, monkeypatch, caplog):
    _, client = inprocess_app
    async def initial(path, env):
        return {"bitcoin": {"idr": 1000}, "ethereum": {"idr": 500}}
    monkeypatch.setattr(crypto, "_fetch_market_json", initial)
    account_id = setup(client)
    add(client, account_id)
    add(client, account_id, "ethereum")
    async def partial(path, env):
        return {"bitcoin": {"idr": 1500}}
    monkeypatch.setattr(crypto, "_fetch_market_json", partial)
    with caplog.at_level(logging.WARNING, logger="crypto"):
        result = client.post(f"/accounts/{account_id}/holdings/refresh-prices").json()
    assert result["failed_coin_ids"] == ["ethereum"]
    records = [record for record in caplog.records if record.name == "crypto"]
    assert len(records) == 1
    assert "reason=missing_quote" in records[0].getMessage()
    assert "ethereum" not in caplog.text
    assert "bitcoin" not in caplog.text


def test_configured_key_is_reported_by_presence_only(inprocess_app, monkeypatch, caplog):
    from app import app
    from auth import require_workspace
    from fastapi import Request
    _, client = inprocess_app
    original = app.dependency_overrides[require_workspace]
    secret = "fictional-api-key-never-log-this"
    async def with_key(request: Request):
        workspace_id = await original(request)
        request.scope["env"].COINGECKO_API_KEY = secret
        return workspace_id
    app.dependency_overrides[require_workspace] = with_key
    async def market(path, env):
        assert env.COINGECKO_API_KEY == secret
        raise crypto.MarketProviderError("http_error", 403)
    monkeypatch.setattr(crypto, "_fetch_market_json", market)
    try:
        account_id = setup(client)
        with caplog.at_level(logging.WARNING, logger="crypto"):
            assert add(client, account_id).status_code == 201
        assert "api_key_configured=True" in caplog.text
        assert "http_status=403" in caplog.text
        assert secret not in caplog.text
        assert "bitcoin" not in caplog.text
    finally:
        app.dependency_overrides[require_workspace] = original
