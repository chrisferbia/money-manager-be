from pathlib import Path

import pytest
from fastapi import HTTPException

from auth import require_subject, require_workspace
from email_import import parse_bca_email
from email_tools import MAX_EMAIL_BYTES, preview_bca_email

pytestmark = pytest.mark.integration
RAW = (Path(__file__).parent / "fixtures/bca-review-fictional.eml").read_bytes().replace(b"\r\n", b"\n")
PATH = "/email-tools/bca/preview"


def snapshot(database):
    return tuple(database.connection.iterdump()), database.connection.total_changes


def test_preview_uses_automatic_parser_and_never_persists_even_on_retries(inprocess_app):
    database, client = inprocess_app
    before = snapshot(database)
    parsed = parse_bca_email(RAW)
    for _ in range(3):
        response = client.post(PATH, content=RAW, headers={"Content-Type": "message/rfc822"})
        assert response.status_code == 200
        result = response.json()
        assert result["persisted"] is False
        assert result["format_valid"] is True
        assert result["warnings"] == []
        assert result["default_category"] == "Other"
        assert result["parsed"]["amount"] == parsed.amount == 35000
        assert result["parsed"]["occurred_at"] == parsed.transaction_date == "2026-10-04T05:00:00Z"
        assert result["parsed"]["counterparty"] == parsed.counterparty
        assert result["parsed"]["reference_number"] == "FICTIONAL-REVIEW-001"
        assert "recipient" not in result["parsed"]
        assert "raw" not in result
        assert snapshot(database) == before


@pytest.mark.parametrize("raw, error", [
    (b"", "non-empty"),
    ((Path(__file__).parent / "fixtures/bca-invalid-fictional.eml").read_bytes(), "Could not read"),
    (RAW.replace(b"IDR", b"USD"), "IDR"),
    (RAW.replace(b"35,000.00", b"invalid"), "Could not read"),
    (RAW.replace(b"04 Oct 2026 12:00:00 WIB", b"invalid date"), "Could not read"),
])
def test_errors_never_save_data(inprocess_app, raw, error):
    database, client = inprocess_app
    before = snapshot(database)
    response = client.post(PATH, content=raw)
    assert response.status_code == 400
    assert error in response.json()["detail"]
    assert snapshot(database) == before


def test_stream_size_limit_never_saves(inprocess_app):
    database, client = inprocess_app
    before = snapshot(database)
    assert client.post(PATH, content=b"x" * (MAX_EMAIL_BYTES + 1)).status_code == 413
    assert snapshot(database) == before


@pytest.mark.parametrize("old, new, warning", [
    (b"Successful", b"Failed", "Transaction status is Failed"),
    (b"Message-ID: <fictional-bca-review-001@example.invalid>\n", b"", "Missing Message-ID"),
])
def test_failed_status_or_missing_id_is_visible_without_importing(inprocess_app, old, new, warning):
    database, client = inprocess_app
    before = snapshot(database)
    response = client.post(PATH, content=RAW.replace(old, new))
    assert response.status_code == 200
    result = response.json()
    assert result["format_valid"] is False
    assert any(warning in value for value in result["warnings"])
    assert snapshot(database) == before


def test_forwarded_sender_can_be_tested_like_automatic_parser(inprocess_app):
    database, client = inprocess_app
    before = snapshot(database)
    result = client.post(PATH, content=RAW.replace(b"bca@bca.co.id", b"forwarder@example.invalid")).json()
    assert result["parsed"]["amount"] == 35000
    assert result["format_valid"] is True
    assert any("authenticity" in warning for warning in result["warnings"])
    assert snapshot(database) == before


def test_preview_is_available_without_accounts_or_review_tables(inprocess_app):
    database, client = inprocess_app
    # Test-only tables: the parser tester must not require the former migration.
    database.connection.executescript("DROP TABLE import_reviews; DROP TABLE merchant_rules;")
    try:
        assert client.post(PATH, content=RAW).status_code == 200
    finally:
        database.connection.executescript((Path(__file__).parents[1] / "migrations/0011_import_review.sql").read_text())


@pytest.mark.parametrize("raw, subtype, direction, category", [
    (RAW.replace(b"Transfer to BCA Account", b"Transfer from BCA Account"), "transfer", "income", "Other Income"),
    (RAW.replace(b"Transfer to BCA Account", b"Transfer to BCA Virtual Account").replace(b"Transfer Amount:", b"Total Payment:"), "virtual_account", "expense", "Other"),
    (RAW.replace(b"Transfer Type:", b"Transaction Type:").replace(b"Transfer to BCA Account", b"QRIS Payment").replace(b"Transfer Amount:", b"Total Payment:").replace(b"Beneficiary Name:", b"Payment to:"), "qris", "expense", "Other"),
    (RAW.replace(b"Transfer to BCA Account", b"Cardless - Withdraw Cash").replace(b"Transfer Amount:", b"Amount:"), "cash_withdrawal", "expense", "Other"),
    (RAW.replace(b"Beneficiary Name:", b"Beneficiary Pocket:"), "account_pocket", "expense", "Other"),
])
def test_supported_formats_are_previewed_without_writes(inprocess_app, raw, subtype, direction, category):
    database, client = inprocess_app
    before = snapshot(database)
    response = client.post(PATH, content=raw)
    assert response.status_code == 200
    result = response.json()
    assert result["parsed"]["amount"] == 35000
    assert result["parsed"]["transaction_subtype"] == subtype
    assert result["parsed"]["direction"] == direction
    assert result["default_category"] == category
    assert response.headers["cache-control"] == "no-store"
    assert snapshot(database) == before


def test_authentication_required(inprocess_app):
    from app import app
    _, client = inprocess_app
    override = app.dependency_overrides.pop(require_workspace)
    def signed_out():
        raise HTTPException(401, "Sign-in required")
    app.dependency_overrides[require_subject] = signed_out
    try:
        assert client.post(PATH, content=RAW).status_code == 401
    finally:
        app.dependency_overrides[require_workspace] = override
        app.dependency_overrides.pop(require_subject, None)


def test_old_review_and_mutation_routes_are_unavailable(inprocess_app):
    database, client = inprocess_app
    before = snapshot(database)
    for method, path in (("GET", "/imports"), ("GET", "/imports/rules"), ("POST", "/imports/bca?account_id=1"), ("POST", "/imports/1/approve"), ("POST", "/imports/1/dismiss"), ("PATCH", "/imports/rules/1"), ("DELETE", "/imports/rules/1")):
        assert client.request(method, path, content=RAW).status_code == 404
    assert snapshot(database) == before


@pytest.mark.unit
def test_preview_service_requires_no_database_and_enforces_limit():
    assert preview_bca_email(RAW)["default_category"] == "Other"
    with pytest.raises(HTTPException):
        preview_bca_email(b"x" * (MAX_EMAIL_BYTES + 1))
