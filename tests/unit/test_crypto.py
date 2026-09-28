import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from crypto import MARKET_USER_AGENT, market_headers, normalize_quantity, value_idr


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
