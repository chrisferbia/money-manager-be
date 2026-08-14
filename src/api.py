from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, Request

from db import (
    account_name_taken,
    account_exists,
    account_balance,
    expenses_by_category,
    category_name_taken,
    category_exists,
    db,
    fetch_account,
    fetch_category,
    fetch_transaction,
    list_transactions,
    transaction_references_account,
    transaction_references_category,
)
from models import (
    Account,
    AccountCreate,
    AccountUpdate,
    Category,
    CategoryCreate,
    CategoryUpdate,
    Transaction,
    TransactionCreate,
    TransactionUpdate,
)
from domain import validate_transaction_rules, validate_transfer_rules

router = APIRouter()


@router.post("/__test/reset", status_code=204)
async def reset_test_database(request: Request):
    if getattr(request.scope["env"], "TEST_MODE", None) != "true":
        raise HTTPException(status_code=404, detail="Not found")

    conn = db(request)
    await conn.prepare("DELETE FROM transactions").run()
    await conn.prepare("DELETE FROM categories").run()
    await conn.prepare("DELETE FROM accounts").run()


def _now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _normalize_occurred_at(value: str | None):
    if not value:
        return _now_iso()

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return _now_iso()

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@router.post("/accounts", status_code=201, response_model=Account)
async def create_account(payload: AccountCreate, request: Request):
    conn = db(request)
    if await account_name_taken(conn, payload.name):
        raise HTTPException(status_code=409, detail="Account name already exists")

    result = (
        await conn.prepare("INSERT INTO accounts (name, type) VALUES (?, ?)")
        .bind(payload.name, payload.type)
        .run()
    )
    return await fetch_account(conn, result.meta.last_row_id)


@router.get("/accounts")
async def list_accounts(request: Request, include_balance: bool = False):
    conn = db(request)
    result = await conn.prepare("SELECT id, name, type, created_at FROM accounts ORDER BY id").all()
    accounts = result.results
    if include_balance:
        return [{**account, "balance": await account_balance(conn, account["id"])} for account in accounts]
    return accounts


@router.get("/accounts/{account_id}/balance")
async def get_account_balance(account_id: int, request: Request):
    conn = db(request)
    if not await account_exists(conn, account_id):
        raise HTTPException(status_code=404, detail="Account not found")
    return {"account_id": account_id, "balance": await account_balance(conn, account_id)}


@router.get("/reports/expenses-by-category")
async def report_expenses_by_category(request: Request, from_: str | None = Query(default=None, alias="from"), to: str | None = Query(default=None, alias="to")):
    conn = db(request)
    return await expenses_by_category(conn, from_, to)


@router.get("/accounts/{account_id}", response_model=Account)
async def get_account(account_id: int, request: Request):
    conn = db(request)
    account = await fetch_account(conn, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    return account


@router.patch("/accounts/{account_id}", response_model=Account)
async def update_account(account_id: int, payload: AccountUpdate, request: Request):
    conn = db(request)
    existing = await fetch_account(conn, account_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Account not found")

    name = payload.name if payload.name is not None else existing["name"]
    type_ = payload.type if payload.type is not None else existing["type"]

    if payload.name is not None and await account_name_taken(conn, name, exclude_id=account_id):
        raise HTTPException(status_code=409, detail="Account name already exists")

    await (
        conn.prepare("UPDATE accounts SET name = ?, type = ? WHERE id = ?")
        .bind(name, type_, account_id)
        .run()
    )
    return await fetch_account(conn, account_id)


@router.delete("/accounts/{account_id}", status_code=204)
async def delete_account(account_id: int, request: Request):
    conn = db(request)
    existing = await fetch_account(conn, account_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Account not found")
    if await transaction_references_account(conn, account_id):
        raise HTTPException(status_code=409, detail="Account has transactions")
    await conn.prepare("DELETE FROM accounts WHERE id = ?").bind(account_id).run()


@router.post("/categories", status_code=201, response_model=Category)
async def create_category(payload: CategoryCreate, request: Request):
    conn = db(request)
    if await category_name_taken(conn, payload.name):
        raise HTTPException(status_code=409, detail="Category name already exists")

    result = (
        await conn.prepare("INSERT INTO categories (name) VALUES (?)")
        .bind(payload.name)
        .run()
    )
    return await fetch_category(conn, result.meta.last_row_id)


@router.get("/categories", response_model=list[Category])
async def list_categories(request: Request):
    conn = db(request)
    result = await conn.prepare("SELECT id, name, created_at FROM categories ORDER BY id").all()
    return result.results


@router.get("/categories/{category_id}", response_model=Category)
async def get_category(category_id: int, request: Request):
    conn = db(request)
    category = await fetch_category(conn, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found")
    return category


@router.patch("/categories/{category_id}", response_model=Category)
async def update_category(category_id: int, payload: CategoryUpdate, request: Request):
    conn = db(request)
    existing = await fetch_category(conn, category_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Category not found")

    name = payload.name if payload.name is not None else existing["name"]

    if payload.name is not None and await category_name_taken(conn, name, exclude_id=category_id):
        raise HTTPException(status_code=409, detail="Category name already exists")

    await conn.prepare("UPDATE categories SET name = ? WHERE id = ?").bind(name, category_id).run()
    return await fetch_category(conn, category_id)


@router.delete("/categories/{category_id}", status_code=204)
async def delete_category(category_id: int, request: Request):
    conn = db(request)
    existing = await fetch_category(conn, category_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Category not found")
    if await transaction_references_category(conn, category_id):
        raise HTTPException(status_code=409, detail="Category has expense transactions")
    await conn.prepare("DELETE FROM categories WHERE id = ?").bind(category_id).run()


@router.post("/transactions", status_code=201, response_model=Transaction)
async def create_transaction(payload: TransactionCreate, request: Request):
    conn = db(request)

    if not await account_exists(conn, payload.account_id):
        raise HTTPException(status_code=404, detail="Account not found")

    try:
        validate_transaction_rules(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    category_id = None
    related_account_id = None
    if payload.type == "expense":
        if not await category_exists(conn, payload.category_id):
            raise HTTPException(status_code=404, detail="Category not found")
        category_id = payload.category_id
    elif payload.type == "transfer":
        if not await account_exists(conn, payload.related_account_id):
            raise HTTPException(status_code=404, detail="Account not found")
        related_account_id = payload.related_account_id

    occurred_at = _normalize_occurred_at(payload.occurred_at)
    description = payload.description if payload.description != "" else None

    result = (
        await conn.prepare(
            "INSERT INTO transactions (type, account_id, category_id, related_account_id, amount, description, occurred_at) VALUES (?, ?, ?, ?, ?, ?, ?)"
        )
        .bind(
            payload.type,
            payload.account_id,
            category_id,
            related_account_id,
            payload.amount,
            description,
            occurred_at,
        )
        .run()
    )
    return await fetch_transaction(conn, result.meta.last_row_id)


async def create_transfer(payload: TransactionCreate, request: Request):
    conn = db(request)

    if not await account_exists(conn, payload.account_id):
        raise HTTPException(status_code=404, detail="Account not found")
    try:
        validate_transfer_rules(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not await account_exists(conn, payload.related_account_id):
        raise HTTPException(status_code=404, detail="Account not found")

    occurred_at = _normalize_occurred_at(payload.occurred_at)
    description = payload.description if payload.description != "" else None
    result = (
        await conn.prepare(
            "INSERT INTO transactions (type, account_id, category_id, related_account_id, amount, description, occurred_at) VALUES (?, ?, NULL, ?, ?, ?, ?)"
        )
        .bind(
            "transfer",
            payload.account_id,
            payload.related_account_id,
            payload.amount,
            description,
            occurred_at,
        )
        .run()
    )
    return await fetch_transaction(conn, result.meta.last_row_id)


@router.get("/transactions", response_model=list[Transaction])
async def list_transaction_route(
    request: Request,
    account_id: int | None = None,
    category_id: int | None = None,
    type_: str | None = Query(default=None, alias="type"),
    from_: str | None = Query(default=None, alias="from"),
    to: str | None = Query(default=None, alias="to"),
): 
    conn = db(request)
    return await list_transactions(conn, account_id, category_id, type_, from_, to)


@router.get("/transactions/{transaction_id}", response_model=Transaction)
async def get_transaction(transaction_id: int, request: Request):
    conn = db(request)
    transaction = await fetch_transaction(conn, transaction_id)
    if transaction is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return transaction


@router.post("/transfers", status_code=201, response_model=Transaction)
async def create_transfer_route(payload: TransactionCreate, request: Request):
    if payload.type != "transfer":
        raise HTTPException(status_code=400, detail="Transfer type is required")
    return await create_transfer(payload, request)


@router.patch("/transactions/{transaction_id}", response_model=Transaction)
async def update_transaction(transaction_id: int, payload: TransactionUpdate, request: Request):
    conn = db(request)
    existing = await fetch_transaction(conn, transaction_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Transaction not found")

    if existing["type"] == "transfer" and "category_id" in payload.model_fields_set:
        raise HTTPException(status_code=400, detail="Transfer transactions cannot have a category")

    amount = payload.amount if payload.amount is not None else existing["amount"]
    description = (
        payload.description if "description" in payload.model_fields_set else existing["description"]
    )
    occurred_at = (
        _normalize_occurred_at(payload.occurred_at)
        if "occurred_at" in payload.model_fields_set
        else existing["occurred_at"]
    )

    if existing["type"] == "income":
        if "category_id" in payload.model_fields_set and payload.category_id is not None:
            raise HTTPException(status_code=400, detail="Income transactions cannot have a category")
        category_id = None
    elif existing["type"] == "expense":
        if "category_id" in payload.model_fields_set:
            if payload.category_id is None:
                raise HTTPException(status_code=400, detail="Expense transactions require a category")
            category_id = payload.category_id
        else:
            category_id = existing["category_id"]
        if category_id is None:
            raise HTTPException(status_code=400, detail="Expense transactions require a category")
        if not await category_exists(conn, category_id):
            raise HTTPException(status_code=404, detail="Category not found")
    else:
        category_id = None
        if existing["related_account_id"] is None:
            raise HTTPException(status_code=400, detail="Transfer transactions require a destination account")

    await (
        conn.prepare("UPDATE transactions SET amount = ?, category_id = ?, description = ?, occurred_at = ? WHERE id = ?")
        .bind(amount, category_id, description, occurred_at, transaction_id)
        .run()
    )
    return await fetch_transaction(conn, transaction_id)


@router.delete("/transactions/{transaction_id}", status_code=204)
async def delete_transaction(transaction_id: int, request: Request):
    conn = db(request)
    existing = await fetch_transaction(conn, transaction_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    await conn.prepare("DELETE FROM transactions WHERE id = ?").bind(transaction_id).run()
