from pathlib import Path
import sqlite3

import pytest

from auth import require_subject, require_workspace
from import_review import MAX_EMAIL_BYTES, normalize_merchant


pytestmark = pytest.mark.integration
FIXTURE = Path(__file__).parent / "fixtures" / "bca-review-fictional.eml"


def email(number=1, merchant="KEDAI CONTOH (FICTIONAL)", **changes):
    text = FIXTURE.read_text().replace("review-001", f"review-{number:03d}").replace("REVIEW-001", f"REVIEW-{number:03d}")
    text = text.replace("KEDAI CONTOH (FICTIONAL)", merchant)
    for old, new in changes.items():
        text = text.replace(old, new)
    return text.encode()


def setup(client):
    account = client.post("/accounts", json={"name": "BCA", "type": "bank"}).json()
    food = client.post("/categories", json={"name": "Food", "type": "expense"}).json()
    shopping = client.post("/categories", json={"name": "Shopping", "type": "expense"}).json()
    return account["id"], food["id"], shopping["id"]


def upload(client, account_id, raw=None, **kwargs):
    return client.post(f"/imports/bca?account_id={account_id}", content=raw if raw is not None else email(), headers={"Content-Type": "message/rfc822", **kwargs})


def approve(client, item_id, account_id, category_id, save_rule=False):
    return client.post(f"/imports/{item_id}/approve", json={"account_id": account_id, "category_id": category_id, "save_rule": save_rule})


def test_review_does_not_affect_ledger_until_approved_and_retries_are_safe(inprocess_app):
    database, client = inprocess_app
    account, food, _ = setup(client)
    response = upload(client, account)
    assert response.status_code == 200
    item = response.json()["item"]
    assert response.json()["duplicate"] is False
    assert item["amount"] == 35000
    assert item["occurred_at"] == "2026-10-04T05:00:00Z"
    assert item["suggested_category_id"] is None
    assert client.get("/transactions").json() == []
    assert client.get("/reports/expenses-by-category").json() == []
    assert client.get(f"/accounts/{account}/balance").json()["balance"] == 0
    repeated = upload(client, account)
    assert repeated.json()["duplicate"] is True
    assert repeated.json()["item"]["id"] == item["id"]
    first = approve(client, item["id"], account, food)
    assert first.status_code == 200
    assert first.json()["status"] == "imported"
    assert approve(client, item["id"], account, food).json()["transaction_id"] == first.json()["transaction_id"]
    transactions = client.get("/transactions").json()
    assert len(transactions) == 1
    assert transactions[0]["amount"] == 35000
    assert transactions[0]["category_id"] == food
    assert client.get("/reports/expenses-by-category").json()[0]["total"] == 35000
    assert client.get(f"/accounts/{account}/balance").json()["balance"] == -35000
    assert client.get("/imports").json() == []
    assert len(client.get("/imports?status=history").json()) == 1
    assert client.get("/imports/rules").json() == []
    stored = dict(database.connection.execute("SELECT * FROM import_reviews").fetchone())
    assert "fictional@example.invalid" not in str(stored)


def test_review_approval_and_saved_rules_work_with_other_category(inprocess_app):
    _, client = inprocess_app
    account, _, _ = setup(client)
    other = client.post("/categories", json={"name": "Other", "type": "expense"}).json()["id"]
    item = upload(client, account).json()["item"]

    response = approve(client, item["id"], account, other, True)

    assert response.status_code == 200
    assert client.get("/transactions").json()[0]["category_id"] == other
    assert client.get("/imports/rules").json()[0]["category_id"] == other
    assert client.get(f"/accounts/{account}/balance").json()["balance"] == -35000
    next_item = upload(client, account, email(2)).json()["item"]
    assert next_item["suggestion_source"] == "rule"
    assert next_item["suggested_category_id"] == other


def test_rules_are_explicit_and_suggestions_follow_approval_history(inprocess_app):
    _, client = inprocess_app
    account, food, shopping = setup(client)
    first = upload(client, account).json()["item"]
    approve(client, first["id"], account, food)
    second = upload(client, account, email(2, "  Kedai Contoh (Fictional) ")).json()["item"]
    assert second["suggestion_source"] == "history"
    assert second["suggested_category_id"] == food
    approve(client, second["id"], account, shopping)
    third = upload(client, account, email(3)).json()["item"]
    assert third["suggested_category_id"] is None
    assert "different categories" in third["suggestion_reason"]
    assert approve(client, third["id"], account, food, True).status_code == 200
    fourth = upload(client, account, email(4)).json()["item"]
    assert fourth["suggestion_source"] == "rule"
    assert fourth["suggested_category_id"] == food
    rule = client.get("/imports/rules").json()[0]
    assert client.patch(f"/imports/rules/{rule['id']}", json={"category_id": shopping}).status_code == 200
    assert client.get("/imports").json()[0]["suggested_category_id"] == shopping
    assert client.delete(f"/imports/rules/{rule['id']}").status_code == 204
    assert client.get("/imports").json()[0]["suggested_category_id"] is None


def test_dismissed_items_remain_deduplicated_and_never_create_transactions(inprocess_app):
    _, client = inprocess_app
    account, food, _ = setup(client)
    item = upload(client, account).json()["item"]
    assert client.post(f"/imports/{item['id']}/dismiss").json()["status"] == "dismissed"
    assert client.post(f"/imports/{item['id']}/dismiss").status_code == 200
    assert approve(client, item["id"], account, food, True).status_code == 409
    assert upload(client, account).json()["item"]["status"] == "dismissed"
    assert client.get("/transactions").json() == []
    assert client.get("/imports/rules").json() == []


def test_duplicate_notification_with_new_message_id_or_missing_id(inprocess_app):
    _, client = inprocess_app
    account, _, _ = setup(client)
    original = upload(client, account).json()["item"]
    changed = email().replace(b"review-001@example", b"another-id@example")
    assert upload(client, account, changed).json()["item"]["id"] == original["id"]
    missing = email().replace(b"Message-ID: <fictional-bca-review-001@example.invalid>\n", b"")
    assert upload(client, account, missing).json()["item"]["id"] == original["id"]
    assert len(client.get("/imports").json()) == 1


@pytest.mark.parametrize("raw, expected", [
    (b"", 400), (b"invalid document", 400), (b"x" * (MAX_EMAIL_BYTES + 1), 413),
    (email(**{"Successful": "Failed"}), 400),
    (email(**{"bca@bca.co.id": "unknown@example.invalid"}), 400),
    (email(**{"IDR 35,000.00": "USD 35.00"}), 400),
], ids=["empty", "invalid", "oversized", "unsuccessful", "wrong-sender", "wrong-currency"])
def test_invalid_uploads_create_no_records(inprocess_app, raw, expected):
    database, client = inprocess_app
    account, _, _ = setup(client)
    assert upload(client, account, raw).status_code == expected
    assert database.connection.execute("SELECT COUNT(*) FROM import_reviews").fetchone()[0] == 0
    assert client.get("/transactions").json() == []


def test_approval_validates_fields_category_direction_and_crypto_accounts(inprocess_app):
    _, client = inprocess_app
    account, food, _ = setup(client)
    item = upload(client, account).json()["item"]
    income = client.post("/categories", json={"name": "Salary", "type": "income"}).json()["id"]
    crypto = client.post("/accounts", json={"name": "Crypto", "type": "investment", "valuation_mode": "crypto"}).json()["id"]
    assert approve(client, item["id"], account, income).status_code == 400
    assert approve(client, item["id"], crypto, food).status_code == 400
    assert upload(client, crypto).status_code == 400
    assert approve(client, item["id"], account, 99999).status_code == 404
    assert client.post(f"/imports/{item['id']}/approve", json={"account_id": account, "category_id": food, "amount": 1}).status_code == 422
    assert client.get("/transactions").json() == []


def test_transfer_like_import_needs_review_and_cannot_create_merchant_rule(inprocess_app):
    _, client = inprocess_app
    account, food, _ = setup(client)
    raw = email(**{"Transfer to BCA Account": "Cardless - Withdraw Cash", "Transfer Amount:": "Amount:"})
    item = upload(client, account, raw).json()["item"]
    assert item["can_save_rule"] is False
    assert "transfer" in item["suggestion_reason"]
    assert approve(client, item["id"], account, food, True).status_code == 400


def test_guessed_import_rule_account_and_category_ids_are_isolated(inprocess_app):
    database, client = inprocess_app
    account, food, _ = setup(client)
    item = upload(client, account).json()["item"]
    approve(client, item["id"], account, food, True)
    rule = client.get("/imports/rules").json()[0]
    pending = upload(client, account, email(2)).json()["item"]
    database.connection.executescript("INSERT INTO users(id,auth_subject) VALUES (2,'bob'); INSERT INTO workspaces(id,owner_user_id,name) VALUES (2,2,'Bob');")
    headers = {"X-Test-Workspace": "2"}
    assert client.get("/imports", headers=headers).json() == []
    assert client.get("/imports/rules", headers=headers).json() == []
    for path in (f"/imports/{pending['id']}/approve", f"/imports/{pending['id']}/dismiss"):
        assert client.post(path, headers=headers, json={"account_id": account, "category_id": food}).status_code == 404
    assert client.patch(f"/imports/rules/{rule['id']}", headers=headers, json={"category_id": food}).status_code == 404
    assert client.delete(f"/imports/rules/{rule['id']}", headers=headers).status_code == 404
    assert upload(client, account, email(), **headers).status_code == 404
    bob_account = client.post("/accounts", headers=headers, json={"name": "BCA", "type": "bank"}).json()["id"]
    bob_category = client.post("/categories", headers=headers, json={"name": "Food", "type": "expense"}).json()["id"]
    bob_item = upload(client, bob_account, email(), **headers).json()["item"]
    assert bob_item["suggested_category_id"] is None
    assert client.post(f"/imports/{bob_item['id']}/approve", headers=headers, json={"account_id": account, "category_id": bob_category}).status_code == 404
    assert client.post(f"/imports/{bob_item['id']}/approve", headers=headers, json={"account_id": bob_account, "category_id": food}).status_code == 404
    with pytest.raises(sqlite3.IntegrityError):
        database.connection.execute("INSERT INTO merchant_rules(workspace_id,merchant_key,merchant_name,direction,category_id) VALUES (2,'x','X','expense',?)", (food,))
    database.connection.rollback()


def test_approval_batch_rolls_back_ledger_when_rule_write_fails(inprocess_app):
    database, client = inprocess_app
    account, food, _ = setup(client)
    item = upload(client, account).json()["item"]
    database.connection.executescript("CREATE TRIGGER fail_rule BEFORE INSERT ON merchant_rules BEGIN SELECT RAISE(ABORT, 'rule failed'); END;")
    try:
        with pytest.raises(sqlite3.IntegrityError):
            approve(client, item["id"], account, food, True)
        assert client.get("/transactions").json() == []
        assert client.get("/imports").json()[0]["status"] == "pending"
    finally:
        database.connection.execute("DROP TRIGGER fail_rule")
        database.connection.commit()


def test_dismiss_racing_with_approval_cannot_write_ledger_or_rule(inprocess_app, monkeypatch):
    database, client = inprocess_app
    account, food, _ = setup(client)
    item = upload(client, account).json()["item"]
    original_batch = database.batch
    async def dismiss_then_batch(statements):
        database.connection.execute("UPDATE import_reviews SET status='dismissed' WHERE id=?", (item["id"],))
        database.connection.commit()
        return await original_batch(statements)
    monkeypatch.setattr(database, "batch", dismiss_then_batch)
    assert approve(client, item["id"], account, food, True).status_code == 409
    assert client.get("/transactions").json() == []
    assert client.get("/imports/rules").json() == []


def test_authentication_is_required_for_all_import_routes(inprocess_app):
    from app import app
    from fastapi import HTTPException
    _, client = inprocess_app
    override = app.dependency_overrides.pop(require_workspace)
    def signed_out():
        raise HTTPException(401, "Sign-in required")
    app.dependency_overrides[require_subject] = signed_out
    try:
        for method, path in (("GET", "/imports"), ("GET", "/imports/rules"), ("POST", "/imports/bca?account_id=1"), ("POST", "/imports/1/approve"), ("POST", "/imports/1/dismiss"), ("PATCH", "/imports/rules/1"), ("DELETE", "/imports/rules/1")):
            assert client.request(method, path, json={"account_id": 1, "category_id": 1}).status_code == 401
    finally:
        app.dependency_overrides[require_workspace] = override
        app.dependency_overrides.pop(require_subject, None)


def test_migration_is_additive_preserves_records_and_matches_fresh_schema(inprocess_app):
    database, client = inprocess_app
    account, food, _ = setup(client)
    tx = client.post("/transactions", json={"type": "expense", "account_id": account, "category_id": food, "amount": 100}).json()
    migration = (Path(__file__).parents[1] / "migrations/0011_import_review.sql").read_text()
    database.connection.executescript(migration)
    assert client.get(f"/transactions/{tx['id']}").json()["amount"] == 100
    assert database.connection.execute("PRAGMA foreign_key_check").fetchall() == []
    legacy = sqlite3.connect(":memory:")
    legacy.execute("PRAGMA foreign_keys = ON")
    schema = (Path(__file__).parents[1] / "db_init.sql").read_text()
    legacy.executescript(schema.split("-- Pending BCA uploads")[0])
    legacy.execute("INSERT INTO transactions (workspace_id,type,account_id,amount) VALUES (1,'income',1,123)")
    legacy.commit()
    legacy.executescript(migration)
    assert legacy.execute("SELECT amount FROM transactions").fetchone()[0] == 123
    assert legacy.execute("PRAGMA foreign_key_check").fetchall() == []
    for table in ("import_reviews", "merchant_rules"):
        assert legacy.execute(f"PRAGMA table_info({table})").fetchall() == [tuple(row) for row in database.connection.execute(f"PRAGMA table_info({table})").fetchall()]


def test_deleting_approved_transaction_does_not_allow_reimport(inprocess_app):
    _, client = inprocess_app
    account, food, _ = setup(client)
    item = upload(client, account).json()["item"]
    approved = approve(client, item["id"], account, food).json()
    assert client.delete(f"/transactions/{approved['transaction_id']}").status_code == 204
    assert upload(client, account).json()["duplicate"] is True
    assert approve(client, item["id"], account, food).json()["transaction_id"] is None
    assert client.get("/transactions").json() == []


def test_pending_account_can_be_deleted_and_replaced_at_approval(inprocess_app):
    _, client = inprocess_app
    account, food, _ = setup(client)
    item = upload(client, account).json()["item"]
    assert client.delete(f"/accounts/{account}").status_code == 204
    assert client.get("/imports").json()[0]["account_id"] is None
    new_account = client.post("/accounts", json={"name": "Bank", "type": "bank"}).json()["id"]
    assert approve(client, item["id"], new_account, food).status_code == 200



@pytest.mark.unit
def test_merchant_normalization_preserves_meaningful_digits():
    assert normalize_merchant("  KOPI-KENANGAN / 01 ") == "kopi kenangan 01"
    assert normalize_merchant("Kopi Kenangan 02") != normalize_merchant("Kopi Kenangan 01")
