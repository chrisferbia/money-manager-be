from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from email import policy
from email.message import Message
from email.parser import BytesParser
from email.utils import parseaddr
from html.parser import HTMLParser
import re

from db import fetch_transaction_by_source_message_id, insert_transaction


BCA_SENDER = "bca@bca.co.id"
BCA_ACCOUNT_NAME = "bca"
INCOME_CATEGORY_NAME = "Other Income"
EXPENSE_CATEGORY_NAME = "Other Expense"

_FIELD_LABELS = (
    "Status",
    "Transaction Date",
    "Transfer Type",
    "Source of Fund",
    "Source Currency",
    "Beneficiary Account",
    "Transfer Currency",
    "Beneficiary Name",
    "Transfer Amount",
    "Transaction Amount",
    "Credit Amount",
    "Debit Amount",
    "Amount",
    "Remarks",
    "Reference No.",
)
_FIELD_LABEL_PATTERN = "|".join(re.escape(label) for label in _FIELD_LABELS)


class EmailImportError(ValueError):
    pass


class _HTMLTextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)

    def text(self):
        return " ".join(" ".join(self.parts).split())


@dataclass
class ParsedBcaEmail:
    message_id: str | None
    sender: str | None
    recipient: str | None
    subject: str | None
    status: str | None
    transaction_date: str | None
    direction: str | None
    amount: int | None
    beneficiary: str | None
    remarks: str | None
    reference_number: str | None
    raw_size: int


def _header(message: Message, name: str) -> str | None:
    value = message.get(name)
    if value is None:
        return None
    return str(value).strip() or None


def _event_header(headers, name: str) -> str | None:
    try:
        value = headers.get(name)
    except (AttributeError, TypeError):
        value = None
    if value is None:
        return None
    return str(value).strip() or None


def _event_value(message, name: str) -> str | None:
    value = getattr(message, name, None)
    if value is None:
        return None
    return str(value).strip() or None


def _nested_messages(message: Message):
    yield message
    for part in message.walk():
        if part is message or part.get_content_type() != "message/rfc822":
            continue
        payload = part.get_payload()
        if isinstance(payload, list):
            for child in payload:
                if isinstance(child, Message):
                    yield from _nested_messages(child)
        elif isinstance(payload, Message):
            yield from _nested_messages(payload)


def _select_original_message(root: Message) -> Message:
    for candidate in _nested_messages(root):
        sender = parseaddr(_header(candidate, "from") or "")[1].lower()
        if sender == BCA_SENDER:
            return candidate
    return root


def _body_text(message: Message) -> str:
    html_body = None
    text_body = None
    for part in message.walk():
        if part.get_content_type() == "text/html" and html_body is None:
            html_body = part.get_content()
        elif part.get_content_type() == "text/plain" and text_body is None:
            text_body = part.get_content()

    body = html_body if html_body is not None else text_body
    if body is None:
        return ""
    if html_body is not None:
        parser = _HTMLTextParser()
        parser.feed(body)
        return parser.text()
    return " ".join(body.split())


def _extract_fields(text: str) -> dict[str, str]:
    fields = {}
    label_pattern = re.compile(
        rf"(?P<label>{_FIELD_LABEL_PATTERN})\s*:", re.IGNORECASE
    )
    matches = list(label_pattern.finditer(text))
    labels_by_case = {label.casefold(): label for label in _FIELD_LABELS}
    for index, match in enumerate(matches):
        value_end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        value = " ".join(text[match.end() : value_end].split()).strip()
        if value:
            fields[labels_by_case[match.group("label").casefold()]] = value
    return fields


def _parse_amount(fields: dict[str, str]) -> int:
    value = next(
        (
            fields.get(label)
            for label in (
                "Transfer Amount",
                "Transaction Amount",
                "Credit Amount",
                "Debit Amount",
                "Amount",
            )
            if fields.get(label)
        ),
        None,
    )
    if value is None:
        raise EmailImportError("Missing transaction amount")

    match = re.search(r"\bIDR\s*([0-9][0-9,]*(?:\.[0-9]+)?)", value, re.IGNORECASE)
    if match is None:
        raise EmailImportError("Transaction amount is not an IDR amount")

    try:
        amount = Decimal(match.group(1).replace(",", ""))
    except InvalidOperation as exc:
        raise EmailImportError("Invalid transaction amount") from exc
    if amount <= 0 or amount != amount.to_integral_value():
        raise EmailImportError("Transaction amount must be a positive whole IDR amount")
    return int(amount)


def _parse_transaction_date(value: str | None) -> str:
    if not value:
        raise EmailImportError("Missing transaction date")

    clean_value = re.sub(r"\s+WIB\s*$", "", value.strip(), flags=re.IGNORECASE)
    parsed = None
    for date_format in ("%d %b %Y %H:%M:%S", "%d %B %Y %H:%M:%S"):
        try:
            parsed = datetime.strptime(clean_value, date_format)
            break
        except ValueError:
            continue
    if parsed is None:
        raise EmailImportError("Invalid transaction date")

    wib = timezone(timedelta(hours=7))
    return parsed.replace(tzinfo=wib).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_direction(value: str | None) -> str:
    if not value:
        raise EmailImportError("Missing transfer type")

    normalized = value.casefold()
    if re.search(r"\b(to|outgoing|debit|payment|withdrawal|purchase)\b", normalized):
        return "expense"
    if re.search(r"\b(from|incoming|credit|deposit|receive|received)\b", normalized):
        return "income"
    raise EmailImportError("Unsupported transfer type")


def parse_bca_email(raw: bytes) -> ParsedBcaEmail:
    try:
        root = BytesParser(policy=policy.default).parsebytes(raw)
    except Exception as exc:
        raise EmailImportError("Unable to parse MIME email") from exc

    original = _select_original_message(root)
    fields = _extract_fields(_body_text(original))
    sender = parseaddr(_header(original, "from") or "")[1].lower() or None
    recipient = _header(original, "to")
    subject = _header(original, "subject")
    status = fields.get("Status")

    if sender != BCA_SENDER:
        return ParsedBcaEmail(
            message_id=_header(original, "message-id"),
            sender=sender,
            recipient=recipient,
            subject=subject,
            status=status,
            transaction_date=None,
            direction=None,
            amount=None,
            beneficiary=None,
            remarks=None,
            reference_number=None,
            raw_size=len(raw),
        )

    direction = _parse_direction(fields.get("Transfer Type"))
    amount = _parse_amount(fields)
    transaction_date = _parse_transaction_date(fields.get("Transaction Date"))

    currency = " ".join(
        fields.get(label, "") for label in ("Source Currency", "Transfer Currency")
    )
    if currency and "IDR" not in currency.upper():
        raise EmailImportError("Only IDR transactions are supported")

    return ParsedBcaEmail(
        message_id=_header(original, "message-id"),
        sender=sender,
        recipient=recipient,
        subject=subject,
        status=status,
        transaction_date=transaction_date,
        direction=direction,
        amount=amount,
        beneficiary=fields.get("Beneficiary Name"),
        remarks=fields.get("Remarks"),
        reference_number=fields.get("Reference No."),
        raw_size=len(raw),
    )


async def _read_raw_email(message) -> bytes:
    raw = getattr(message, "raw", None)
    if isinstance(raw, bytes):
        return raw
    if isinstance(raw, str):
        return raw.encode()

    array_buffer = getattr(raw, "arrayBuffer", None)
    if callable(array_buffer):
        value = await array_buffer()
    else:
        import js

        value = await js.Response.new(raw).arrayBuffer()

    if hasattr(value, "to_bytes"):
        return value.to_bytes()
    if hasattr(value, "to_py"):
        value = value.to_py()
    return bytes(value)


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


async def _find_import(conn, message_id: str):
    return (
        await conn.prepare(
            "SELECT id, status, transaction_id FROM email_imports WHERE message_id = ?"
        )
        .bind(message_id)
        .first()
    )


async def _insert_import_log(conn, parsed: ParsedBcaEmail, status: str, reason: str | None):
    result = (
        await conn.prepare(
            "INSERT INTO email_imports (message_id, sender, recipient, subject, received_at, status, reason, raw_size, reference_number) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
        )
        .bind(
            parsed.message_id,
            parsed.sender,
            parsed.recipient,
            parsed.subject,
            _now_iso(),
            status,
            reason,
            parsed.raw_size,
            parsed.reference_number,
        )
        .run()
    )
    return result.meta.last_row_id


async def _update_import_log(
    conn, import_id: int, status: str, reason: str | None = None, transaction_id: int | None = None
):
    await (
        conn.prepare(
            "UPDATE email_imports SET status = ?, reason = ?, transaction_id = ? WHERE id = ?"
        )
        .bind(status, reason, transaction_id, import_id)
        .run()
    )


async def _record_review(conn, parsed: ParsedBcaEmail, reason: str):
    if parsed.message_id:
        existing = await _find_import(conn, parsed.message_id)
        if existing:
            print(
                "Email import:",
                {
                    "status": "duplicate",
                    "message_id": parsed.message_id,
                    "transaction_id": existing["transaction_id"],
                },
            )
            return
    await _insert_import_log(conn, parsed, "review", reason)
    print(
        "Email import:",
        {"status": "review", "message_id": parsed.message_id, "reason": reason},
    )


def _description(parsed: ParsedBcaEmail) -> str:
    if parsed.beneficiary:
        description = f"BCA transaction with {parsed.beneficiary}"
    else:
        description = "BCA transaction"
    if parsed.remarks and parsed.remarks != "-":
        description += f"; Remarks: {parsed.remarks}"
    return description


def _event_metadata(message) -> ParsedBcaEmail:
    headers = getattr(message, "headers", {})
    return ParsedBcaEmail(
        message_id=_event_header(headers, "message-id"),
        sender=parseaddr(_event_header(headers, "from") or "")[1].lower() or None,
        recipient=_event_value(message, "to") or _event_header(headers, "to"),
        subject=_event_header(headers, "subject"),
        status=None,
        transaction_date=None,
        direction=None,
        amount=None,
        beneficiary=None,
        remarks=None,
        reference_number=None,
        raw_size=int(getattr(message, "rawSize", 0) or 0),
    )


async def process_email(message, env):
    metadata = _event_metadata(message)
    try:
        raw = await _read_raw_email(message)
        parsed = parse_bca_email(raw)
        if not parsed.recipient:
            parsed.recipient = metadata.recipient
        if not parsed.subject:
            parsed.subject = metadata.subject
        if not parsed.message_id:
            parsed.message_id = metadata.message_id
        if not parsed.raw_size:
            parsed.raw_size = metadata.raw_size or len(raw)
    except EmailImportError as exc:
        parsed = metadata
        await _record_review(env.money_manager, parsed, str(exc))
        return

    conn = env.money_manager
    if parsed.message_id:
        existing = await _find_import(conn, parsed.message_id)
        if existing:
            print(
                "Email import:",
                {
                    "status": "duplicate",
                    "message_id": parsed.message_id,
                    "transaction_id": existing["transaction_id"],
                },
            )
            return

    if parsed.sender != BCA_SENDER:
        reason = "Sender is not an approved BCA address"
        await _record_review(conn, parsed, reason)
        return

    if not parsed.message_id:
        await _record_review(conn, parsed, "Missing Message-ID")
        return

    if (parsed.status or "").casefold() not in {"successful", "success", "completed", "succeeded"}:
        reason = f"Transaction status is {parsed.status or 'missing'}"
        await _record_review(conn, parsed, reason)
        return

    import_id = await _insert_import_log(conn, parsed, "processing", None)
    try:
        account = (
            await conn.prepare("SELECT id FROM accounts WHERE name = ?")
            .bind(BCA_ACCOUNT_NAME)
            .first()
        )
        if account is None:
            raise EmailImportError("Account 'bca' was not found")

        category_name = (
            INCOME_CATEGORY_NAME if parsed.direction == "income" else EXPENSE_CATEGORY_NAME
        )
        category = (
            await conn.prepare("SELECT id FROM categories WHERE name = ? AND type = ?")
            .bind(category_name, parsed.direction)
            .first()
        )
        if category is None:
            raise EmailImportError(f"Category '{category_name}' was not found")

        transaction_id = await insert_transaction(
            conn,
            parsed.direction,
            account["id"],
            category["id"],
            parsed.amount,
            _description(parsed),
            parsed.transaction_date,
            parsed.message_id,
        )
    except EmailImportError as exc:
        await _update_import_log(conn, import_id, "failed", str(exc))
        print(
            "Email import:",
            {"status": "failed", "message_id": parsed.message_id, "reason": str(exc)},
        )
        return
    except Exception as exc:
        existing_transaction = None
        if parsed.message_id:
            existing_transaction = await fetch_transaction_by_source_message_id(
                conn, parsed.message_id
            )
        if existing_transaction:
            await _update_import_log(
                conn,
                import_id,
                "duplicate",
                "Transaction already exists for this message ID",
                existing_transaction["id"],
            )
            print(
                "Email import:",
                {
                    "status": "duplicate",
                    "message_id": parsed.message_id,
                    "transaction_id": existing_transaction["id"],
                },
            )
            return
        await _update_import_log(conn, import_id, "failed", "Transaction insert failed")
        print(
            "Email import:",
            {"status": "failed", "message_id": parsed.message_id, "reason": "Transaction insert failed"},
        )
        return

    await _update_import_log(conn, import_id, "imported", None, transaction_id)
    print(
        "Email import:",
        {
            "status": "imported",
            "message_id": parsed.message_id,
            "transaction_id": transaction_id,
            "type": parsed.direction,
            "amount": parsed.amount,
        },
    )
