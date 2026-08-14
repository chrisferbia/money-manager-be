def validate_transaction_rules(payload):
    """Validate rules that do not require a database lookup."""
    if payload.type == "income":
        if payload.category_id is not None:
            raise ValueError("Income transactions cannot have a category")
    elif payload.type == "expense":
        if payload.category_id is None:
            raise ValueError("Expense transactions require a category")
    else:
        validate_transfer_rules(payload)


def validate_transfer_rules(payload):
    """Validate transfer-specific fields without checking D1 state."""
    if payload.category_id is not None:
        raise ValueError("Transfer transactions cannot have a category")
    if payload.related_account_id is None:
        raise ValueError("Transfer transactions require a destination account")
    if payload.related_account_id == payload.account_id:
        raise ValueError("Transfer accounts must differ")
