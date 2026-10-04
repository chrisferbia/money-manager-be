"""Authenticated, non-persisting previews of the production BCA email parser."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from auth import require_workspace
from email_import import (
    BCA_SENDER, EXPENSE_CATEGORY_NAME, INCOME_CATEGORY_NAME,
    EmailImportError, parse_bca_email,
)

router = APIRouter(prefix="/email-tools", dependencies=[Depends(require_workspace)])
MAX_EMAIL_BYTES = 1024 * 1024


def preview_bca_email(raw: bytes):
    if not raw or len(raw) > MAX_EMAIL_BYTES:
        raise HTTPException(400, "Choose a non-empty .eml file of 1 MB or less")
    try:
        parsed = parse_bca_email(raw)
    except (EmailImportError, ValueError, LookupError, UnicodeError) as exc:
        raise HTTPException(400, f"Could not read this BCA notification: {exc}") from exc
    warnings = []
    if not parsed.message_id:
        warnings.append("Missing Message-ID: automatic import would not create a transaction.")
    if (parsed.status or "").casefold() not in {"successful", "success", "completed", "succeeded"}:
        warnings.append(f"Transaction status is {parsed.status or 'missing'}: automatic import would not create a transaction.")
    if parsed.direction not in {"income", "expense"}:
        warnings.append("Unsupported transaction direction: automatic import would not create a transaction.")
    format_valid = not warnings
    if parsed.sender != BCA_SENDER:
        warnings.append("Sender is not bca@bca.co.id. Forwarded messages may have a different sender; parsing does not verify authenticity.")
    return {
        "parsed": {
            "subject": parsed.subject,
            "sender": parsed.sender,
            "message_id": parsed.message_id,
            "status": parsed.status,
            "occurred_at": parsed.transaction_date,
            "direction": parsed.direction,
            "amount": parsed.amount,
            "counterparty": parsed.counterparty,
            "description": parsed.remarks,
            "reference_number": parsed.reference_number,
            "transaction_subtype": parsed.transaction_subtype,
        },
        "default_category": INCOME_CATEGORY_NAME if parsed.direction == "income" else EXPENSE_CATEGORY_NAME,
        "format_valid": format_valid,
        "warnings": warnings,
        "persisted": False,
    }


@router.post("/bca/preview")
async def preview_bca(request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    raw = bytearray()
    async for chunk in request.stream():
        if len(raw) + len(chunk) > MAX_EMAIL_BYTES:
            raise HTTPException(413, "The email must be 1 MB or less")
        raw.extend(chunk)
    # Deliberately no D1 access, import log, queue, merchant rule or ledger write.
    return preview_bca_email(bytes(raw))
