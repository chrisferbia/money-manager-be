import asyncio
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from email_import import parse_bca_email, process_email
from fake_d1 import FakeD1


pytestmark = pytest.mark.unit

SCHEMA = (Path(__file__).parents[2] / "db_init.sql").read_text()
MIGRATION = (Path(__file__).parents[2] / "migrations/0004_email_transaction_import.sql").read_text()


def bca_email(
    *,
    message_id="<bca-test@example.com>",
    sender="BCA <bca@bca.co.id>",
    status="Successful",
    transfer_type="Transfer to BCA Account",
    transaction_date="29 Aug 2026 14:18:52",
    amount="IDR 30,000.00",
    beneficiary="TJU SIAT LI",
    remarks="-",
    reference="00B3F2F7-FF98-4BD1-8135-05E55BC4191D",
):
    return f"""From: {sender}
To: CHRISFERBIA@GMAIL.COM
Message-ID: {message_id}
Subject: Internet Transaction Journal
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="boundary"

--boundary
Content-Type: text/html; charset=utf-8

<html><body>
<table>
<tr><td>Status</td><td>:</td><td>{status}</td></tr>
<tr><td>Transaction Date</td><td>:</td><td>{transaction_date}</td></tr>
<tr><td>Transfer Type</td><td>:</td><td>{transfer_type}</td></tr>
<tr><td>Source Currency</td><td>:</td><td>IDR - Indonesian Rupiah</td></tr>
<tr><td>Transfer Currency</td><td>:</td><td>IDR - Indonesian Rupiah</td></tr>
<tr><td>Beneficiary Name</td><td>:</td><td>{beneficiary}</td></tr>
<tr><td>Transfer Amount</td><td>:</td><td>{amount}</td></tr>
<tr><td>Remarks</td><td>:</td><td>{remarks}</td></tr>
<tr><td>Reference No.</td><td>:</td><td>{reference}</td></tr>
</table>
</body></html>
--boundary--
""".encode()


def make_message(raw):
    return SimpleNamespace(raw=raw, headers={}, to="transaction@example.com", rawSize=len(raw))


def make_database(with_bca=True):
    database = FakeD1(SCHEMA)
    if with_bca:
        database.connection.execute("INSERT INTO accounts (name, type) VALUES ('BCA', 'cash')")
        database.connection.commit()
    return database


def run_import(database, raw):
    asyncio.run(process_email(make_message(raw), SimpleNamespace(money_manager=database)))


def test_ac1_parser_reads_forwarded_multipart_bca_email():
    parsed = parse_bca_email(bca_email())

    assert parsed.sender == "bca@bca.co.id"
    assert parsed.subject == "Internet Transaction Journal"
    assert parsed.direction == "expense"
    assert parsed.amount == 30000
    assert parsed.transaction_date == "2026-08-29T07:18:52Z"


def test_ac1_parser_finds_bca_message_inside_forwarded_attachment():
    original = bca_email()
    forwarded = (
        b"From: Gmail <forwarder@gmail.com>\n"
        b"To: transaction@example.com\n"
        b"Subject: Fwd: Internet Transaction Journal\n"
        b"Content-Type: multipart/mixed; boundary=outer\n\n"
        b"--outer\n"
        b"Content-Type: message/rfc822\n\n"
        + original
        + b"\n--outer--\n"
    )

    parsed = parse_bca_email(forwarded)

    assert parsed.sender == "bca@bca.co.id"
    assert parsed.message_id == "<bca-test@example.com>"


def test_ac1_parser_reads_bca_content_from_gmail_forwarder():
    parsed = parse_bca_email(bca_email(sender="Gmail <forwarder@gmail.com>"))

    assert parsed.sender == "forwarder@gmail.com"
    assert parsed.direction == "expense"
    assert parsed.transaction_subtype == "transfer"


@pytest.mark.parametrize(
    "filename, expected_subtype, expected_amount, expected_counterparty",
    [
        ("Transfer to BCA Account.eml", "transfer", 30000, "TJU SIAT LI"),
        (
            "Transfer to BCA Virtual Account.eml",
            "virtual_account",
            50000,
            "PT VISIONET INTERNASIONAL / OVO",
        ),
        ("Transfer to BCA Account Pocket.eml", "account_pocket", 17000000, "Savings"),
        ("QRIS Payment.eml", "qris", 20000, "FOODCOURT PASIR PUTIH"),
        ("Cardless - Withdraw Cash.eml", "cash_withdrawal", 500000, "Cash withdrawal"),
    ],
)
def test_ac1_parser_reads_all_documented_bca_formats(
    filename, expected_subtype, expected_amount, expected_counterparty
):
    raw = (Path(__file__).parents[2] / "docs" / "email_format" / filename).read_bytes()

    parsed = parse_bca_email(raw)

    assert parsed.sender == "bca@bca.co.id"
    assert parsed.direction == "expense"
    assert parsed.transaction_subtype == expected_subtype
    assert parsed.amount == expected_amount
    assert parsed.counterparty == expected_counterparty


def test_ac2_ac3_imports_outgoing_transaction_with_reference():
    database = make_database()

    run_import(database, bca_email())

    transaction = database.connection.execute(
        "SELECT id, type, account_id, category_id, amount, counterparty, description, occurred_at, source_message_id, transaction_subtype FROM transactions"
    ).fetchone()
    import_log = database.connection.execute(
        "SELECT status, transaction_id, reference_number FROM email_imports"
    ).fetchone()
    category = database.connection.execute(
        "SELECT name FROM categories WHERE id = ?", (transaction[3],)
    ).fetchone()

    account_id = database.connection.execute(
        "SELECT id FROM accounts WHERE name = 'BCA'"
    ).fetchone()[0]
    assert transaction[1] == "expense"
    assert transaction[2] == account_id
    assert transaction[4] == 30000
    assert transaction[5] == "TJU SIAT LI"
    assert transaction[6] is None
    assert transaction[7] == "2026-08-29T07:18:52Z"
    assert transaction[8] == "<bca-test@example.com>"
    assert transaction[9] == "transfer"
    assert category[0] == "Other Expense"
    assert tuple(import_log) == ("imported", transaction[0], "00B3F2F7-FF98-4BD1-8135-05E55BC4191D")


@pytest.mark.parametrize(
    "filename, expected_subtype, expected_amount, expected_counterparty",
    [
        ("Transfer to BCA Account.eml", "transfer", 30000, "TJU SIAT LI"),
        (
            "Transfer to BCA Virtual Account.eml",
            "virtual_account",
            50000,
            "PT VISIONET INTERNASIONAL / OVO",
        ),
        ("Transfer to BCA Account Pocket.eml", "account_pocket", 17000000, "Savings"),
        ("QRIS Payment.eml", "qris", 20000, "FOODCOURT PASIR PUTIH"),
        ("Cardless - Withdraw Cash.eml", "cash_withdrawal", 500000, "Cash withdrawal"),
    ],
)
def test_ac2_all_documented_formats_create_expenses(
    filename, expected_subtype, expected_amount, expected_counterparty
):
    database = make_database()
    raw = (Path(__file__).parents[2] / "docs" / "email_format" / filename).read_bytes()

    run_import(database, raw)

    transaction = database.connection.execute(
        "SELECT type, transaction_subtype, amount, counterparty FROM transactions"
    ).fetchone()
    assert tuple(transaction) == (
        "expense",
        expected_subtype,
        expected_amount,
        expected_counterparty,
    )


def test_ac4_imports_incoming_transaction_as_income():
    database = make_database()

    run_import(
        database,
        bca_email(
            message_id="<incoming@example.com>",
            transfer_type="Transfer from BCA Account",
        ),
    )

    transaction = database.connection.execute(
        "SELECT type, category_id, transaction_subtype FROM transactions"
    ).fetchone()
    category = database.connection.execute(
        "SELECT name FROM categories WHERE id = ?", (transaction[1],)
    ).fetchone()
    assert tuple(transaction)[0] == "income"
    assert category[0] == "Other Income"
    assert transaction[2] == "transfer"


def test_ac5_duplicate_message_id_does_not_insert_again(capsys):
    database = make_database()
    raw = bca_email()

    run_import(database, raw)
    run_import(database, raw)

    count = database.connection.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    assert count == 1
    assert "'status': 'duplicate'" in capsys.readouterr().out


def test_ac6_unknown_sender_is_logged_without_transaction():
    database = make_database()

    run_import(
        database,
        bca_email(
            sender="Unknown <unknown@example.com>",
            transfer_type="Unknown Activity",
        ),
    )

    assert database.connection.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 0
    review = database.connection.execute("SELECT status, reason FROM email_imports").fetchone()
    assert tuple(review) == ("review", "Unsupported transfer type")


def test_ac6_repeated_review_email_is_reported_as_duplicate(capsys):
    database = make_database()
    raw = bca_email(
        sender="Unknown <unknown@example.com>",
        transfer_type="Unknown Activity",
    )

    run_import(database, raw)
    run_import(database, raw)

    assert database.connection.execute("SELECT COUNT(*) FROM email_imports").fetchone()[0] == 1
    assert "'status': 'duplicate'" in capsys.readouterr().out


@pytest.mark.parametrize(
    "email_kwargs, expected_reason",
    [
        ({"status": "Failed"}, "Transaction status is Failed"),
        ({"transfer_type": "Unknown Activity"}, "Unsupported transfer type"),
        ({"transaction_date": ""}, "Missing transaction date"),
    ],
)
def test_ac7_unsupported_or_invalid_email_is_logged(email_kwargs, expected_reason):
    database = make_database()

    run_import(database, bca_email(**email_kwargs))

    assert database.connection.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 0
    review = database.connection.execute("SELECT status, reason FROM email_imports").fetchone()
    assert tuple(review) == ("review", expected_reason)


def test_ac8_missing_account_is_recorded_as_failed():
    database = make_database(with_bca=False)

    run_import(database, bca_email())

    assert database.connection.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 0
    failure = database.connection.execute("SELECT status, reason FROM email_imports").fetchone()
    assert tuple(failure) == ("failed", "Account 'BCA' was not found")


def test_ac8_missing_default_category_is_recorded_as_failed():
    database = make_database()
    database.connection.execute(
        "DELETE FROM categories WHERE name = 'Other Expense' AND type = 'expense'"
    )
    database.connection.commit()

    run_import(database, bca_email())

    assert database.connection.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 0
    failure = database.connection.execute("SELECT status, reason FROM email_imports").fetchone()
    assert tuple(failure) == ("failed", "Category 'Other Expense' was not found")


def test_ac7_missing_message_id_is_logged_without_transaction():
    database = make_database()

    run_import(database, bca_email(message_id=""))

    assert database.connection.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 0
    review = database.connection.execute("SELECT status, reason FROM email_imports").fetchone()
    assert tuple(review) == ("review", "Missing Message-ID")


def test_ac9_import_does_not_forward_or_reject():
    class Message:
        def __init__(self, raw):
            self.raw = raw
            self.headers = {}
            self.to = "transaction@example.com"
            self.rawSize = len(raw)

        def forward(self, *_args):
            raise AssertionError("forward must not be called")

        def setReject(self, *_args):
            raise AssertionError("setReject must not be called")

    database = make_database()
    asyncio.run(process_email(Message(bca_email()), SimpleNamespace(money_manager=database)))

    assert database.connection.execute("SELECT status FROM email_imports").fetchone()[0] == "imported"


def test_ac10_import_migration_preserves_transactions_and_delete_behavior():
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(
        """
        CREATE TABLE accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            type TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            type TEXT NOT NULL DEFAULT 'expense',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL,
            account_id INTEGER NOT NULL REFERENCES accounts(id),
            category_id INTEGER REFERENCES categories(id),
            related_account_id INTEGER REFERENCES accounts(id),
            amount INTEGER NOT NULL,
            description TEXT,
            occurred_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        INSERT INTO accounts (name, type) VALUES ('bca', 'cash');
        INSERT INTO transactions (type, account_id, amount) VALUES ('income', 1, 100);
        """
    )

    connection.executescript(MIGRATION)
    connection.execute(
        "INSERT INTO email_imports (message_id, status, transaction_id) VALUES (?, ?, ?)",
        ("<migration@example.com>", "imported", 1),
    )
    connection.execute("DELETE FROM transactions WHERE id = 1")

    assert connection.execute("SELECT amount FROM transactions WHERE id = 1").fetchone() is None
    assert connection.execute(
        "SELECT transaction_id FROM email_imports WHERE message_id = ?",
        ("<migration@example.com>",),
    ).fetchone()[0] is None
