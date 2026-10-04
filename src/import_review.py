"""Manual BCA email review, separate from the existing automatic email importer."""

import hashlib
import json
import re
import unicodedata
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from auth import require_workspace
from db import db, fetch_account, fetch_category, fetch_transaction_by_source_message_id
from email_import import BCA_SENDER, EmailImportError, parse_bca_email


router = APIRouter(prefix="/imports", dependencies=[Depends(require_workspace)])
MAX_EMAIL_BYTES = 1024 * 1024
TRANSFER_SUBTYPES = {"cash_withdrawal", "account_pocket"}
GENERIC_MERCHANTS = {"", "bca transfer", "bca virtual account", "qris payment", "cash withdrawal", "bca account pocket"}


class ApproveImport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account_id: int = Field(gt=0)
    category_id: int = Field(gt=0)
    save_rule: bool = False


class UpdateRule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category_id: int = Field(gt=0)


def normalize_merchant(value: str | None) -> str:
    # Preserve digits and words: similar merchant names should not silently merge.
    text = unicodedata.normalize("NFKC", value or "").casefold()
    return " ".join(re.sub(r"[^\w\s]", " ", text).split())


def can_save_rule(item) -> bool:
    return item["merchant_key"] not in GENERIC_MERCHANTS and item["transaction_subtype"] not in TRANSFER_SUBTYPES


async def _ledger_account(conn, account_id):
    account = await fetch_account(conn, account_id)
    if account is None:
        raise HTTPException(404, "Account not found")
    if account["valuation_mode"] != "ledger":
        raise HTTPException(400, "Choose an account that records transactions")
    return account


async def _category(conn, category_id, direction):
    category = await fetch_category(conn, category_id)
    if category is None:
        raise HTTPException(404, "Category not found")
    if category["type"] != direction:
        raise HTTPException(400, "Category must match the transaction type")
    return category


async def _find(conn, import_id):
    item = await conn.prepare("SELECT * FROM import_reviews WHERE workspace_id = ? AND id = ?").bind(conn.workspace_id, import_id).first()
    if item is None:
        raise HTTPException(404, "Import not found")
    return item


async def _suggest(conn, item):
    result = dict(item)
    result.pop("workspace_id", None)
    result.pop("fingerprint", None)
    result.pop("message_id", None)
    result.pop("merchant_key", None)
    result.update(suggested_category_id=None, suggestion_source="none", can_save_rule=can_save_rule(item))
    result["suggestion_reason"] = "Choose a category. No matching rule or previous approval."
    if item["status"] != "pending":
        return result
    if item["transaction_subtype"] in TRANSFER_SUBTYPES:
        result["suggestion_reason"] = "This may be a transfer between your accounts. Skip it and record a transfer if needed."
        return result
    if not can_save_rule(item):
        result["suggestion_reason"] = "The notification does not identify a specific merchant. Choose a category."
        return result
    rule = await conn.prepare(
        "SELECT r.category_id FROM merchant_rules r JOIN categories c ON c.workspace_id = r.workspace_id AND c.id = r.category_id "
        "WHERE r.workspace_id = ? AND r.merchant_key = ? AND r.direction = ? AND c.type = ?"
    ).bind(conn.workspace_id, item["merchant_key"], item["direction"], item["direction"]).first()
    if rule:
        result.update(suggested_category_id=rule["category_id"], suggestion_source="rule", suggestion_reason="Matches your saved merchant rule.")
        return result
    history = await conn.prepare(
        "SELECT DISTINCT t.category_id FROM import_reviews i "
        "JOIN transactions t ON t.workspace_id = i.workspace_id AND t.id = i.transaction_id "
        "JOIN categories c ON c.workspace_id = t.workspace_id AND c.id = t.category_id "
        "WHERE i.workspace_id = ? AND i.merchant_key = ? AND i.direction = ? AND i.status = 'imported' "
        "AND t.type = ? AND c.type = ?"
    ).bind(conn.workspace_id, item["merchant_key"], item["direction"], item["direction"], item["direction"]).all()
    if len(history.results) == 1:
        result.update(suggested_category_id=history.results[0]["category_id"], suggestion_source="history", suggestion_reason="You previously approved this category for the same merchant. Please check it.")
    elif len(history.results) > 1:
        result["suggestion_reason"] = "Previous approvals used different categories for this merchant. Choose a category."
    return result


async def stage_bca_email(conn, raw: bytes, account_id: int):
    """Reusable staging service for authenticated uploads and future tenant-addressed mail."""
    await _ledger_account(conn, account_id)
    if not raw or len(raw) > MAX_EMAIL_BYTES:
        raise HTTPException(400, "Choose a non-empty .eml file of 1 MB or less")
    try:
        parsed = parse_bca_email(raw)
    except (EmailImportError, ValueError, LookupError, UnicodeError) as exc:
        raise HTTPException(400, f"Could not read this BCA notification: {exc}") from exc
    # This is a user-uploaded document, not authenticated inbound email. Sender
    # matching identifies the format; future inbound routing must verify delivery.
    if parsed.sender != BCA_SENDER:
        raise HTTPException(400, "Upload the original BCA notification email (.eml)")
    if (parsed.status or "").casefold() not in {"successful", "success", "completed", "succeeded"}:
        raise HTTPException(400, "Only successful BCA transactions can be reviewed")
    if parsed.amount > 9_007_199_254_740_991:
        raise HTTPException(400, "The transaction amount is too large")
    if any(len(value or "") > maximum for value, maximum in (
        (parsed.counterparty, 200), (parsed.remarks, 1000), (parsed.message_id, 500), (parsed.reference_number, 200),
    )):
        raise HTTPException(400, "This notification contains fields that are too long")
    merchant_key = normalize_merchant(parsed.counterparty)
    description = parsed.remarks if parsed.remarks and parsed.remarks != "-" else None
    fingerprint = hashlib.sha256(json.dumps([
        parsed.direction, parsed.transaction_date, parsed.amount, merchant_key,
        parsed.reference_number, parsed.transaction_subtype,
    ], ensure_ascii=False).encode()).hexdigest()
    if parsed.message_id and await fetch_transaction_by_source_message_id(conn, parsed.message_id):
        raise HTTPException(409, "This notification was already imported")
    # INSERT OR IGNORE and lookup remain safe for concurrent upload retries.
    inserted = await conn.prepare(
        "INSERT OR IGNORE INTO import_reviews (workspace_id, account_id, message_id, fingerprint, reference_number, "
        "direction, amount, counterparty, merchant_key, description, occurred_at, transaction_subtype) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    ).bind(conn.workspace_id, account_id, parsed.message_id, fingerprint, parsed.reference_number,
           parsed.direction, parsed.amount, parsed.counterparty, merchant_key, description,
           parsed.transaction_date, parsed.transaction_subtype).run()
    item = await conn.prepare(
        "SELECT * FROM import_reviews WHERE workspace_id = ? AND (fingerprint = ? "
        "OR (message_id IS NOT NULL AND message_id = ?) "
        "OR (reference_number IS NOT NULL AND reference_number = ? AND direction = ? AND occurred_at = ?)) "
        "ORDER BY id LIMIT 1"
    ).bind(conn.workspace_id, fingerprint, parsed.message_id, parsed.reference_number, parsed.direction, parsed.transaction_date).first()
    return {"item": await _suggest(conn, item), "duplicate": inserted.meta.changes == 0}


@router.post("/bca")
async def upload_bca(request: Request, account_id: int = Query(gt=0)):
    raw = bytearray()
    async for chunk in request.stream():
        if len(raw) + len(chunk) > MAX_EMAIL_BYTES:
            raise HTTPException(413, "The email must be 1 MB or less")
        raw.extend(chunk)
    return await stage_bca_email(db(request), bytes(raw), account_id)


@router.get("")
async def list_imports(request: Request, status: Literal["pending", "history"] = "pending", limit: int = Query(default=100, ge=1, le=100)):
    conn = db(request)
    condition = "status = 'pending'" if status == "pending" else "status != 'pending'"
    rows = await conn.prepare(
        f"SELECT * FROM import_reviews WHERE workspace_id = ? AND {condition} ORDER BY id DESC LIMIT ?"
    ).bind(conn.workspace_id, limit).all()
    return [await _suggest(conn, row) for row in rows.results]


@router.post("/{import_id}/approve")
async def approve_import(import_id: int, payload: ApproveImport, request: Request):
    conn = db(request)
    item = await _find(conn, import_id)
    if item["status"] == "imported":
        return await _suggest(conn, item)
    if item["status"] != "pending":
        raise HTTPException(409, "This import was already skipped")
    await _ledger_account(conn, payload.account_id)
    await _category(conn, payload.category_id, item["direction"])
    if payload.save_rule and not can_save_rule(item):
        raise HTTPException(400, "A merchant rule cannot be saved for this notification")
    source_id = f"bca-review:{import_id}"
    statements = [conn.prepare(
        "INSERT INTO transactions (workspace_id, type, account_id, category_id, amount, counterparty, description, "
        "occurred_at, transaction_subtype, source_message_id) "
        "SELECT workspace_id, direction, ?, ?, amount, counterparty, description, occurred_at, transaction_subtype, ? "
        "FROM import_reviews WHERE workspace_id = ? AND id = ? AND status = 'pending'"
    ).bind(payload.account_id, payload.category_id, source_id, conn.workspace_id, import_id)]
    if payload.save_rule:
        statements.append(conn.prepare(
            "INSERT INTO merchant_rules (workspace_id, merchant_key, merchant_name, direction, category_id) "
            "SELECT workspace_id, merchant_key, counterparty, direction, ? FROM import_reviews "
            "WHERE workspace_id = ? AND id = ? AND status = 'pending' "
            "ON CONFLICT(workspace_id, merchant_key, direction) DO UPDATE "
            "SET category_id = excluded.category_id, merchant_name = excluded.merchant_name"
        ).bind(payload.category_id, conn.workspace_id, import_id))
    statements.append(conn.prepare(
        "UPDATE import_reviews SET status = 'imported', account_id = ?, reviewed_at = CURRENT_TIMESTAMP, "
        "transaction_id = (SELECT id FROM transactions WHERE workspace_id = ? AND source_message_id = ?) "
        "WHERE workspace_id = ? AND id = ? AND status = 'pending'"
    ).bind(payload.account_id, conn.workspace_id, source_id, conn.workspace_id, import_id))
    # Approval, optional learning, and the ledger write commit or roll back together.
    await conn.batch(statements)
    result = await _find(conn, import_id)
    if result["status"] != "imported":
        raise HTTPException(409, "This import was already skipped")
    return await _suggest(conn, result)


@router.post("/{import_id}/dismiss")
async def dismiss_import(import_id: int, request: Request):
    conn = db(request)
    item = await _find(conn, import_id)
    if item["status"] == "imported":
        raise HTTPException(409, "This import was already approved")
    await conn.prepare(
        "UPDATE import_reviews SET status = 'dismissed', reviewed_at = CURRENT_TIMESTAMP "
        "WHERE workspace_id = ? AND id = ? AND status = 'pending'"
    ).bind(conn.workspace_id, import_id).run()
    result = await _find(conn, import_id)
    if result["status"] == "imported":
        raise HTTPException(409, "This import was already approved")
    return await _suggest(conn, result)


@router.get("/rules")
async def list_rules(request: Request):
    conn = db(request)
    rows = await conn.prepare(
        "SELECT r.id, r.merchant_name, r.direction, r.category_id FROM merchant_rules r "
        "WHERE r.workspace_id = ? ORDER BY r.merchant_name, r.id"
    ).bind(conn.workspace_id).all()
    return list(rows.results)


@router.patch("/rules/{rule_id}")
async def update_rule(rule_id: int, payload: UpdateRule, request: Request):
    conn = db(request)
    rule = await conn.prepare("SELECT * FROM merchant_rules WHERE workspace_id = ? AND id = ?").bind(conn.workspace_id, rule_id).first()
    if rule is None:
        raise HTTPException(404, "Rule not found")
    await _category(conn, payload.category_id, rule["direction"])
    await conn.prepare("UPDATE merchant_rules SET category_id = ? WHERE workspace_id = ? AND id = ?").bind(payload.category_id, conn.workspace_id, rule_id).run()
    return {"id": rule_id, "merchant_name": rule["merchant_name"], "direction": rule["direction"], "category_id": payload.category_id}


@router.delete("/rules/{rule_id}", status_code=204)
async def delete_rule(rule_id: int, request: Request):
    conn = db(request)
    rule = await conn.prepare("SELECT id FROM merchant_rules WHERE workspace_id = ? AND id = ?").bind(conn.workspace_id, rule_id).first()
    if rule is None:
        raise HTTPException(404, "Rule not found")
    await conn.prepare("DELETE FROM merchant_rules WHERE workspace_id = ? AND id = ?").bind(conn.workspace_id, rule_id).run()
    return Response(status_code=204)
