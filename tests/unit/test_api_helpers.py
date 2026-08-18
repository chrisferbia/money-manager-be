from api import _normalize_occurred_at
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
