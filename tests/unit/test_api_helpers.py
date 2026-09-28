from datetime import datetime, timezone

from api import _normalize_occurred_at
from db import build_savings_balance_history, recent_month_keys
from ui import _month_bounds
import pytest


pytestmark = pytest.mark.unit


def test_normalize_occurred_at_defaults_to_current_utc_timestamp():
    normalized = _normalize_occurred_at(None)

    assert normalized.endswith("Z")
    assert "T" in normalized
    assert "." not in normalized


def test_normalize_occurred_at_converts_offset_to_utc():
    assert _normalize_occurred_at("2026-08-10T12:00:00+02:00") == "2026-08-10T10:00:00Z"


def test_normalize_occurred_at_converts_zulu_timestamp():
    assert _normalize_occurred_at("2026-08-10T10:00:00Z") == "2026-08-10T10:00:00Z"


def test_normalize_occurred_at_assumes_utc_for_naive_timestamp():
    assert _normalize_occurred_at("2026-08-10T10:00:00") == "2026-08-10T10:00:00Z"


def test_normalize_occurred_at_falls_back_for_invalid_timestamp():
    normalized = _normalize_occurred_at("not-a-date")

    assert normalized.endswith("Z")
    assert "T" in normalized


def test_month_bounds_cover_the_full_selected_month():
    assert _month_bounds("2026-02") == (
        "2026-02-01T00:00:00Z",
        "2026-02-28T23:59:59Z",
    )


def test_month_bounds_reject_invalid_month():
    assert _month_bounds("2026-13") == (None, None)


def test_recent_month_keys_crosses_year_boundary():
    assert recent_month_keys(4, datetime(2026, 2, 10, tzinfo=timezone.utc)) == [
        "2025-11",
        "2025-12",
        "2026-01",
        "2026-02",
    ]


def test_savings_history_carries_opening_balance_and_fills_empty_months():
    history = build_savings_balance_history(
        [
            {"month": "2025-12", "change": 500},
            {"month": "2026-02", "change": 200},
            {"month": "2026-04", "change": -75},
        ],
        ["2026-01", "2026-02", "2026-03", "2026-04"],
    )

    assert history == [
        {"month": "2026-01", "balance": 500, "change": 0},
        {"month": "2026-02", "balance": 700, "change": 200},
        {"month": "2026-03", "balance": 700, "change": 0},
        {"month": "2026-04", "balance": 625, "change": -75},
    ]
