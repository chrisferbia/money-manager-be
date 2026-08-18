import pytest

from domain import validate_transaction_rules, validate_transfer_rules
from models import TransactionCreate


pytestmark = pytest.mark.unit


def test_income_may_have_category():
    payload = TransactionCreate(type="income", account_id=1, amount=100, category_id=2)

    validate_transaction_rules(payload)


def test_expense_requires_category():
    payload = TransactionCreate(type="expense", account_id=1, amount=100)

    with pytest.raises(ValueError, match="require a category"):
        validate_transaction_rules(payload)


def test_transfer_requires_destination_account():
    payload = TransactionCreate(type="transfer", account_id=1, amount=100)

    with pytest.raises(ValueError, match="require a destination"):
        validate_transaction_rules(payload)


def test_transfer_accounts_must_differ():
    payload = TransactionCreate(
        type="transfer", account_id=1, related_account_id=1, amount=100
    )

    with pytest.raises(ValueError, match="must differ"):
        validate_transfer_rules(payload)


def test_transfer_cannot_have_category():
    payload = TransactionCreate(
        type="transfer", account_id=1, related_account_id=2, category_id=3, amount=100
    )

    with pytest.raises(ValueError, match="cannot have a category"):
        validate_transfer_rules(payload)


def test_valid_transaction_rules_are_accepted():
    validate_transaction_rules(TransactionCreate(type="income", account_id=1, amount=100))
    validate_transaction_rules(
        TransactionCreate(type="expense", account_id=1, category_id=2, amount=100)
    )
    validate_transaction_rules(
        TransactionCreate(type="transfer", account_id=1, related_account_id=2, amount=100)
    )
