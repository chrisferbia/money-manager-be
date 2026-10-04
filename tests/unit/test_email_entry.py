import asyncio
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import email_import
from fake_d1 import FakeD1


pytestmark = pytest.mark.unit
ROOT = Path(__file__).parents[2]


@pytest.fixture
def entrypoint(monkeypatch):
    # The SDK base class is only available in Pyodide. Keep the real email handler.
    monkeypatch.setitem(sys.modules, "workers", SimpleNamespace(WorkerEntrypoint=object))
    specification = importlib.util.spec_from_file_location("email_entry_test", ROOT / "src" / "entry.py")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module.Default


@pytest.mark.parametrize("explicit_env", [False, True])
def test_email_handler_awaits_existing_importer_with_correct_environment(entrypoint, monkeypatch, explicit_env):
    importer = AsyncMock()
    monkeypatch.setattr(email_import, "process_email", importer)
    bound_env = SimpleNamespace(label="bound")
    supplied_env = SimpleNamespace(label="supplied")
    message = object()

    asyncio.run(entrypoint.email(
        SimpleNamespace(env=bound_env), message, supplied_env if explicit_env else None
    ))

    importer.assert_awaited_once_with(message, supplied_env if explicit_env else bound_env)


def test_email_handler_does_not_hide_importer_errors(entrypoint, monkeypatch):
    monkeypatch.setattr(email_import, "process_email", AsyncMock(side_effect=RuntimeError("test failure")))
    with pytest.raises(RuntimeError, match="test failure"):
        asyncio.run(entrypoint.email(SimpleNamespace(env=object()), object()))


def test_reconnected_handler_imports_into_claimed_workspace_one_and_deduplicates(entrypoint):
    database = FakeD1((ROOT / "db_init.sql").read_text())
    database.connection.executescript(
        "INSERT INTO users (id, auth_subject) VALUES (7, 'fictional-personal-user');"
        "UPDATE workspaces SET owner_user_id = 7 WHERE id = 1;"
        "INSERT INTO accounts (workspace_id, name, type) VALUES (1, 'BCA', 'bank');"
        "INSERT INTO categories (workspace_id, name, type) VALUES (1, 'Other', 'expense');"
        "INSERT INTO users (id, auth_subject) VALUES (8, 'fictional-other-user');"
        "INSERT INTO workspaces (id, owner_user_id, name) VALUES (2, 8, 'Other workspace');"
        "INSERT INTO accounts (workspace_id, name, type) VALUES (2, 'BCA', 'bank');"
        "INSERT INTO categories (workspace_id, name, type) VALUES (2, 'Other', 'expense');"
    )
    raw = (
        "From: BCA <bca@bca.co.id>\r\nTo: import@example.com\r\n"
        "Message-ID: <fictional-reconnected@example.com>\r\n"
        "Subject: Internet Transaction Journal\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n\r\n"
        "Status: Successful\r\nTransaction Date: 04 Oct 2026 12:00:00\r\n"
        "Transfer Type: Transfer to BCA Account\r\nSource Currency: IDR\r\n"
        "Beneficiary Name: Fictional Merchant\r\nTransfer Amount: IDR 30,000.00\r\n"
        "Remarks: -\r\nReference No.: fictional-reference\r\n"
    ).encode()
    message = SimpleNamespace(raw=raw, headers={}, to="import@example.com", rawSize=len(raw))
    worker = SimpleNamespace(env=SimpleNamespace(money_manager=database))

    asyncio.run(entrypoint.email(worker, message))
    asyncio.run(entrypoint.email(worker, message))

    transactions = database.connection.execute(
        "SELECT t.workspace_id, t.type, t.amount, a.name, c.name FROM transactions t "
        "JOIN accounts a ON a.id = t.account_id JOIN categories c ON c.id = t.category_id"
    ).fetchall()
    assert [tuple(row) for row in transactions] == [(1, "expense", 30000, "BCA", "Other")]
    assert tuple(database.connection.execute(
        "SELECT workspace_id, status FROM email_imports"
    ).fetchone()) == (1, "imported")
    assert database.connection.execute("PRAGMA foreign_key_check").fetchall() == []
