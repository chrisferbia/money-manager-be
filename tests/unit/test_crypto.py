import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from crypto import MARKET_USER_AGENT, _is_fresh, market_headers, normalize_quantity, value_idr
from datetime import datetime, timedelta, timezone


pytestmark = pytest.mark.unit


@pytest.mark.parametrize("raw,expected", [
    ("0.00000001", "0.00000001"),
    ("1.5000", "1.5"),
    ("100", "100"),
])
def test_quantity_preserves_precision(raw, expected):
    assert normalize_quantity(raw) == expected


@pytest.mark.parametrize("raw", ["0", "-1", "1e2", "0.1234567890123456789", "NaN", "01"])
def test_quantity_rejects_invalid_values(raw):
    with pytest.raises(ValueError):
        normalize_quantity(raw)


def test_value_rounds_to_nearest_idr():
    assert value_idr("0.00000001", "1500000000") == 15
    assert value_idr("0.5", "1") == 1


def test_market_request_identifies_app_and_keeps_optional_key_server_side():
    assert market_headers(SimpleNamespace())["User-Agent"] == MARKET_USER_AGENT
    assert market_headers(SimpleNamespace(COINGECKO_API_KEY="demo"))["x-cg-demo-api-key"] == "demo"


def test_existing_database_migration_adds_crypto_schema():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE accounts (id INTEGER PRIMARY KEY, name TEXT, type TEXT, sequence INTEGER, created_at TEXT)")
    conn.execute("INSERT INTO accounts VALUES (1, 'Investment', 'investment', 1, '2026-01-01')")
    migration = Path(__file__).parents[2] / "migrations" / "0009_crypto_holdings.sql"
    conn.executescript(migration.read_text())
    assert conn.execute("SELECT valuation_mode FROM accounts WHERE id = 1").fetchone()[0] == "ledger"
    assert conn.execute("SELECT COUNT(*) FROM crypto_holdings").fetchone()[0] == 0


def test_freshness_uses_configured_expiry_and_handles_invalid_dates():
    now = datetime.now(timezone.utc)
    five_minutes_ago = (now - timedelta(minutes=5)).isoformat()
    assert _is_fresh(five_minutes_ago, now, 600)
    assert not _is_fresh(five_minutes_ago, now, 60)
    assert not _is_fresh(five_minutes_ago, now, 300)
    for value in (None, "invalid", "2020-01-01T00:00:00", (now + timedelta(seconds=1)).isoformat()):
        assert not _is_fresh(value, now, 600)


def test_expiry_migration_preserves_workspace_and_adds_default_with_limits():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE workspaces (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO workspaces VALUES (1, 'Fictional workspace')")
    conn.executescript((Path(__file__).parents[2] / "migrations/0013_crypto_price_expiry.sql").read_text())
    assert conn.execute("SELECT name,crypto_price_expiry_minutes FROM workspaces").fetchone() == ("Fictional workspace", 10)
    conn.execute("INSERT INTO workspaces (id,name) VALUES (2,'New fictional workspace')")
    assert conn.execute("SELECT crypto_price_expiry_minutes FROM workspaces WHERE id=2").fetchone()[0] == 10
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE workspaces SET crypto_price_expiry_minutes=0 WHERE id=1")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE workspaces SET crypto_price_expiry_minutes=1441 WHERE id=1")
