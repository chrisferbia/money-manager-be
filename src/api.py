from datetime import datetime, timezone
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from auth import require_workspace

from db import (
    account_name_taken,
    account_exists,
    account_balance,
    expenses_by_category,
    category_name_taken,
    category_exists,
    category_matches_type,
    db,
    fetch_account,
    fetch_category,
    fetch_transaction,
    list_transactions,
    list_transaction_descriptions,
    next_sequence,
    reorder,
    savings_balance_history,
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
    CryptoHoldingCreate,
    CryptoHoldingUpdate,
)
from domain import validate_transaction_rules, validate_transfer_rules
from crypto import COIN_ID_RE, account_holdings, normalize_quantity, refresh_prices, search_coins

router = APIRouter(dependencies=[Depends(require_workspace)])
logger = logging.getLogger(__name__)


async def _require_ledger_account(conn, account_id: int):
    account = await fetch_account(conn, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    if account["valuation_mode"] == "crypto":
        raise HTTPException(status_code=400, detail="Crypto accounts are valued from holdings, not transactions")


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
    if payload.valuation_mode == "crypto" and payload.type != "investment":
        raise HTTPException(status_code=400, detail="Crypto tracking requires an Investment account")
    if await account_name_taken(conn, payload.name):
        raise HTTPException(status_code=409, detail="Account name already exists")

    result = (
        await conn.prepare("INSERT INTO accounts (workspace_id, name, type, sequence, valuation_mode) VALUES (?, ?, ?, ?, ?)")
        .bind(conn.workspace_id, payload.name, payload.type, await next_sequence(conn, "accounts"), payload.valuation_mode)
        .run()
    )
    if payload.sequence is not None:
        await reorder(conn, "accounts", result.meta.last_row_id, payload.sequence)
    return await fetch_account(conn, result.meta.last_row_id)


@router.get("/accounts")
async def list_accounts(request: Request, include_balance: bool = False):
    conn = db(request)
    result = await conn.prepare(
        "SELECT id, name, type, sequence, valuation_mode, created_at FROM accounts WHERE workspace_id = ? ORDER BY sequence, id"
    ).bind(conn.workspace_id).all()
    accounts = result.results
    if include_balance:
        coins = await conn.prepare("SELECT DISTINCT coin_id FROM crypto_holdings WHERE workspace_id = ?").bind(conn.workspace_id).all()
        await refresh_prices(conn, request.scope["env"], [row["coin_id"] for row in coins.results])
        return [{**account, "balance": await account_balance(conn, account["id"])} for account in accounts]
    return accounts


@router.get("/accounts/{account_id}/balance")
async def get_account_balance(account_id: int, request: Request):
    conn = db(request)
    if not await account_exists(conn, account_id):
        raise HTTPException(status_code=404, detail="Account not found")
    coins = await conn.prepare("SELECT coin_id FROM crypto_holdings WHERE workspace_id = ? AND account_id = ?").bind(conn.workspace_id, account_id).all()
    await refresh_prices(conn, request.scope["env"], [row["coin_id"] for row in coins.results])
    return {"account_id": account_id, "balance": await account_balance(conn, account_id)}


@router.get("/reports/expenses-by-category")
async def report_expenses_by_category(request: Request, from_: str | None = Query(default=None, alias="from"), to: str | None = Query(default=None, alias="to")):
    conn = db(request)
    return await expenses_by_category(conn, from_, to)


@router.get("/reports/savings-balance-history")
async def report_savings_balance_history(
    request: Request,
    months: int = Query(default=12, ge=2, le=60),
):
    return await savings_balance_history(db(request), months)


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
    valuation_mode = payload.valuation_mode if payload.valuation_mode is not None else existing["valuation_mode"]
    if valuation_mode == "crypto" and type_ != "investment":
        raise HTTPException(status_code=400, detail="Crypto tracking requires an Investment account")
    if existing["valuation_mode"] == "crypto" and valuation_mode != "crypto":
        holdings = await conn.prepare("SELECT id FROM crypto_holdings WHERE workspace_id = ? AND account_id = ? LIMIT 1").bind(conn.workspace_id, account_id).first()
        if holdings:
            raise HTTPException(status_code=409, detail="Remove crypto holdings before disabling crypto tracking")
    if existing["valuation_mode"] != "crypto" and valuation_mode == "crypto":
        ledger_balance = await account_balance(conn, account_id)
        if ledger_balance != 0 and not payload.confirm_ledger_replacement:
            raise HTTPException(status_code=409, detail="Confirm replacing the existing transaction balance with crypto holdings value")

    if payload.name is not None and await account_name_taken(conn, name, exclude_id=account_id):
        raise HTTPException(status_code=409, detail="Account name already exists")

    await (
        conn.prepare("UPDATE accounts SET name = ?, type = ?, valuation_mode = ? WHERE workspace_id = ? AND id = ?")
        .bind(name, type_, valuation_mode, conn.workspace_id, account_id)
        .run()
    )
    if payload.sequence is not None:
        await reorder(conn, "accounts", account_id, payload.sequence)
    return await fetch_account(conn, account_id)


@router.delete("/accounts/{account_id}", status_code=204)
async def delete_account(account_id: int, request: Request):
    conn = db(request)
    existing = await fetch_account(conn, account_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Account not found")
    if await transaction_references_account(conn, account_id):
        raise HTTPException(status_code=409, detail="Account has transactions")
    if await conn.prepare("SELECT id FROM crypto_holdings WHERE workspace_id = ? AND account_id = ? LIMIT 1").bind(conn.workspace_id, account_id).first():
        raise HTTPException(status_code=409, detail="Account has crypto holdings")
    await conn.prepare("DELETE FROM accounts WHERE workspace_id = ? AND id = ?").bind(conn.workspace_id, account_id).run()


@router.get("/crypto/search")
async def crypto_search(request: Request, q: str = Query(min_length=2, max_length=80)):
    if len(q.strip()) < 2:
        raise HTTPException(status_code=400, detail="Enter at least two search characters")
    try:
        return await search_coins(q.strip(), request.scope["env"])
    except Exception as exc:
        logger.exception("Coin search provider request failed")
        raise HTTPException(status_code=503, detail="Coin search is temporarily unavailable") from exc


@router.get("/accounts/{account_id}/holdings")
async def list_crypto_holdings(account_id: int, request: Request):
    conn = db(request)
    account = await fetch_account(conn, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    if account["valuation_mode"] != "crypto":
        raise HTTPException(status_code=400, detail="Account does not track crypto holdings")
    coins = await conn.prepare("SELECT coin_id FROM crypto_holdings WHERE workspace_id = ? AND account_id = ?").bind(conn.workspace_id, account_id).all()
    await refresh_prices(conn, request.scope["env"], [row["coin_id"] for row in coins.results])
    return await account_holdings(conn, account_id)


@router.post("/accounts/{account_id}/holdings", status_code=201)
async def add_crypto_holding(account_id: int, payload: CryptoHoldingCreate, request: Request):
    conn = db(request)
    account = await fetch_account(conn, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    if account["valuation_mode"] != "crypto":
        raise HTTPException(status_code=400, detail="Account does not track crypto holdings")
    if not COIN_ID_RE.fullmatch(payload.coin_id):
        raise HTTPException(status_code=400, detail="Invalid coin ID")
    if not payload.name.strip() or not payload.symbol.strip():
        raise HTTPException(status_code=400, detail="Coin name and symbol are required")
    try:
        quantity = normalize_quantity(payload.quantity)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    existing = await conn.prepare("SELECT id FROM crypto_holdings WHERE workspace_id = ? AND account_id = ? AND coin_id = ?").bind(conn.workspace_id, account_id, payload.coin_id).first()
    if existing:
        raise HTTPException(status_code=409, detail="Coin already exists in this account; edit its quantity")
    result = await (
        conn.prepare("INSERT INTO crypto_holdings (workspace_id, account_id, coin_id, name, symbol, quantity) VALUES (?, ?, ?, ?, ?, ?)")
        .bind(conn.workspace_id, account_id, payload.coin_id, payload.name.strip(), payload.symbol.strip().upper(), quantity)
        .run()
    )
    await refresh_prices(conn, request.scope["env"], [payload.coin_id])
    holdings = await account_holdings(conn, account_id)
    return next(row for row in holdings if row["id"] == result.meta.last_row_id)


@router.patch("/accounts/{account_id}/holdings/{holding_id}")
async def update_crypto_holding(account_id: int, holding_id: int, payload: CryptoHoldingUpdate, request: Request):
    conn = db(request)
    existing = await conn.prepare("SELECT id FROM crypto_holdings WHERE workspace_id = ? AND id = ? AND account_id = ?").bind(conn.workspace_id, holding_id, account_id).first()
    if existing is None:
        raise HTTPException(status_code=404, detail="Holding not found")
    try:
        quantity = normalize_quantity(payload.quantity)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await conn.prepare("UPDATE crypto_holdings SET quantity = ? WHERE workspace_id = ? AND id = ?").bind(quantity, conn.workspace_id, holding_id).run()
    return next(row for row in await account_holdings(conn, account_id) if row["id"] == holding_id)


@router.delete("/accounts/{account_id}/holdings/{holding_id}", status_code=204)
async def delete_crypto_holding(account_id: int, holding_id: int, request: Request):
    conn = db(request)
    existing = await conn.prepare("SELECT id FROM crypto_holdings WHERE workspace_id = ? AND id = ? AND account_id = ?").bind(conn.workspace_id, holding_id, account_id).first()
    if existing is None:
        raise HTTPException(status_code=404, detail="Holding not found")
    await conn.prepare("DELETE FROM crypto_holdings WHERE workspace_id = ? AND id = ?").bind(conn.workspace_id, holding_id).run()


@router.post("/categories", status_code=201, response_model=Category)
async def create_category(payload: CategoryCreate, request: Request):
    conn = db(request)
    if await category_name_taken(conn, payload.name):
        raise HTTPException(status_code=409, detail="Category name already exists")
    if payload.type != "expense" and payload.monthly_budget is not None:
        raise HTTPException(status_code=400, detail="Only expense categories can have a budget")

    result = (
        await conn.prepare(
            "INSERT INTO categories (workspace_id, name, type, sequence, monthly_budget) VALUES (?, ?, ?, ?, ?)"
        )
        .bind(
            conn.workspace_id,
            payload.name,
            payload.type,
            await next_sequence(conn, "categories"),
            payload.monthly_budget,
        )
        .run()
    )
    if payload.sequence is not None:
        await reorder(conn, "categories", result.meta.last_row_id, payload.sequence)
    return await fetch_category(conn, result.meta.last_row_id)


@router.get("/categories", response_model=list[Category])
async def list_categories(request: Request):
    conn = db(request)
    result = await conn.prepare(
        "SELECT id, name, type, sequence, monthly_budget, created_at FROM categories WHERE workspace_id = ? ORDER BY sequence, id"
    ).bind(conn.workspace_id).all()
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
    if (
        "monthly_budget" in payload.model_fields_set
        and payload.monthly_budget is not None
        and existing["type"] != "expense"
    ):
        raise HTTPException(status_code=400, detail="Only expense categories can have a budget")

    monthly_budget = (
        payload.monthly_budget
        if "monthly_budget" in payload.model_fields_set
        else existing["monthly_budget"]
    )
    await conn.prepare(
        "UPDATE categories SET name = ?, monthly_budget = ? WHERE workspace_id = ? AND id = ?"
    ).bind(name, monthly_budget, conn.workspace_id, category_id).run()
    if payload.sequence is not None:
        await reorder(conn, "categories", category_id, payload.sequence)
    return await fetch_category(conn, category_id)


@router.delete("/categories/{category_id}", status_code=204)
async def delete_category(category_id: int, request: Request):
    conn = db(request)
    existing = await fetch_category(conn, category_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Category not found")
    if await transaction_references_category(conn, category_id):
        raise HTTPException(status_code=409, detail="Category has expense transactions")
    await conn.prepare("DELETE FROM categories WHERE workspace_id = ? AND id = ?").bind(conn.workspace_id, category_id).run()


@router.post("/transactions", status_code=201, response_model=Transaction)
async def create_transaction(payload: TransactionCreate, request: Request):
    conn = db(request)
    await _require_ledger_account(conn, payload.account_id)

    try:
        validate_transaction_rules(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    category_id = None
    related_account_id = None
    if payload.type in ("income", "expense"):
        if payload.type == "expense" and payload.category_id is None:
            raise HTTPException(status_code=400, detail="Expense transactions require a category")
        if payload.category_id is not None:
            if not await category_exists(conn, payload.category_id):
                raise HTTPException(status_code=404, detail="Category not found")
            if not await category_matches_type(conn, payload.category_id, payload.type):
                raise HTTPException(status_code=400, detail="Category type must match transaction type")
        category_id = payload.category_id
    elif payload.type == "transfer":
        await _require_ledger_account(conn, payload.related_account_id)
        related_account_id = payload.related_account_id

    occurred_at = _normalize_occurred_at(payload.occurred_at)
    counterparty = payload.counterparty if payload.counterparty != "" else None
    description = payload.description if payload.description != "" else None

    result = (
        await conn.prepare(
            "INSERT INTO transactions (workspace_id, type, account_id, category_id, related_account_id, amount, counterparty, description, occurred_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
        )
        .bind(
            conn.workspace_id,
            payload.type,
            payload.account_id,
            category_id,
            related_account_id,
            payload.amount,
            counterparty,
            description,
            occurred_at,
        )
        .run()
    )
    return await fetch_transaction(conn, result.meta.last_row_id)


async def create_transfer(payload: TransactionCreate, request: Request):
    conn = db(request)
    await _require_ledger_account(conn, payload.account_id)
    try:
        validate_transfer_rules(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await _require_ledger_account(conn, payload.related_account_id)

    occurred_at = _normalize_occurred_at(payload.occurred_at)
    counterparty = payload.counterparty if payload.counterparty != "" else None
    description = payload.description if payload.description != "" else None
    result = (
        await conn.prepare(
            "INSERT INTO transactions (workspace_id, type, account_id, category_id, related_account_id, amount, counterparty, description, occurred_at) VALUES (?, ?, ?, NULL, ?, ?, ?, ?, ?)"
        )
        .bind(
            conn.workspace_id,
            "transfer",
            payload.account_id,
            payload.related_account_id,
            payload.amount,
            counterparty,
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


@router.get("/transactions/descriptions", response_model=list[str])
async def transaction_description_suggestions(
    request: Request,
    q: str = Query(default="", description="Literal substring to match; surrounding whitespace is ignored. Matching is ASCII case-insensitive."),
    limit: int = Query(default=20, ge=1, le=100, description="Maximum number of suggestions."),
):
    """Suggest distinct descriptions from currently saved transactions.

    Excludes null and empty descriptions and trims surrounding spaces.
    Deduplication is case-sensitive; sorting is ASCII case-insensitive.
    Omit q to return the first suggestions alphabetically.
    """
    return await list_transaction_descriptions(db(request), q, limit)


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

    transaction_type = (
        payload.type if "type" in payload.model_fields_set else existing["type"]
    )
    account_id = (
        payload.account_id
        if "account_id" in payload.model_fields_set
        else existing["account_id"]
    )
    related_account_id = (
        payload.related_account_id
        if "related_account_id" in payload.model_fields_set
        else existing["related_account_id"]
    )
    amount = payload.amount if payload.amount is not None else existing["amount"]
    description = (
        payload.description if "description" in payload.model_fields_set else existing["description"]
    )
    counterparty = (
        payload.counterparty if "counterparty" in payload.model_fields_set else existing["counterparty"]
    )
    if counterparty == "":
        counterparty = None
    occurred_at = (
        _normalize_occurred_at(payload.occurred_at)
        if "occurred_at" in payload.model_fields_set
        else existing["occurred_at"]
    )

    if account_id is None:
        raise HTTPException(status_code=400, detail="Account is required")
    await _require_ledger_account(conn, account_id)

    if transaction_type == "transfer":
        if "category_id" in payload.model_fields_set and payload.category_id is not None:
            raise HTTPException(status_code=400, detail="Transfer transactions cannot have a category")
        if related_account_id is None:
            raise HTTPException(status_code=400, detail="Transfer transactions require a destination account")
        if related_account_id == account_id:
            raise HTTPException(status_code=400, detail="Transfer accounts must differ")
        await _require_ledger_account(conn, related_account_id)
        category_id = None
    else:
        if "related_account_id" in payload.model_fields_set and payload.related_account_id is not None:
            raise HTTPException(status_code=400, detail="Only transfer transactions can have a destination account")
        related_account_id = None
        if "category_id" in payload.model_fields_set:
            category_id = payload.category_id
        elif transaction_type != existing["type"]:
            category_id = None
        else:
            category_id = existing["category_id"]
        if transaction_type == "expense" and category_id is None:
            raise HTTPException(status_code=400, detail="Expense transactions require a category")
        if category_id is not None:
            if not await category_exists(conn, category_id):
                raise HTTPException(status_code=404, detail="Category not found")
            if not await category_matches_type(conn, category_id, transaction_type):
                raise HTTPException(status_code=400, detail="Category type must match transaction type")

    await (
        conn.prepare(
            "UPDATE transactions SET type = ?, account_id = ?, category_id = ?, related_account_id = ?, amount = ?, counterparty = ?, description = ?, occurred_at = ? WHERE workspace_id = ? AND id = ?"
        )
        .bind(
            transaction_type,
            account_id,
            category_id,
            related_account_id,
            amount,
            counterparty,
            description,
            occurred_at,
            conn.workspace_id,
            transaction_id,
        )
        .run()
    )
    return await fetch_transaction(conn, transaction_id)


@router.delete("/transactions/{transaction_id}", status_code=204)
async def delete_transaction(transaction_id: int, request: Request):
    conn = db(request)
    existing = await fetch_transaction(conn, transaction_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    await conn.prepare("DELETE FROM transactions WHERE workspace_id = ? AND id = ?").bind(conn.workspace_id, transaction_id).run()
