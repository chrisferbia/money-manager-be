import pytest
from pydantic import ValidationError

from models import (
    AccountCreate,
    CategoryCreate,
    TransactionCreate,
    TransactionUpdate,
)


pytestmark = pytest.mark.unit


def test_account_create_requires_non_empty_name_and_type():
    with pytest.raises(ValidationError):
        AccountCreate(name="", type="cash")
    with pytest.raises(ValidationError):
        AccountCreate(name="Cash", type="")


def test_category_create_requires_non_empty_name():
    with pytest.raises(ValidationError):
        CategoryCreate(name="")


def test_transaction_create_requires_positive_amount():
    with pytest.raises(ValidationError):
        TransactionCreate(type="income", account_id=1, amount=0)


def test_transaction_create_accepts_supported_types():
    for type_ in ("income", "expense", "transfer"):
        transaction = TransactionCreate(type=type_, account_id=1, amount=100)
        assert transaction.type == type_


def test_transaction_create_rejects_unknown_type():
    with pytest.raises(ValidationError):
        TransactionCreate(type="refund", account_id=1, amount=100)


def test_transaction_update_rejects_immutable_fields():
    with pytest.raises(ValidationError):
        TransactionUpdate(account_id=2)
