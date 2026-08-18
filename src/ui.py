import calendar
import jinja2
import templates
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError

from api import (
    create_account,
    create_category,
    create_transfer,
    create_transaction,
    delete_account,
    delete_category,
    delete_transaction,
    update_account,
    update_category,
    update_transaction,
)
from db import db, expenses_by_category, fetch_account, fetch_category, fetch_transaction, list_transactions, list_accounts_with_balance
from models import (
    AccountCreate,
    AccountUpdate,
    CategoryCreate,
    CategoryUpdate,
    TransactionCreate,
    TransactionUpdate,
)

router = APIRouter()

jinja_env = jinja2.Environment(
    loader=jinja2.DictLoader(templates.TEMPLATES), autoescape=True
)


def _dashboard_bound(value: str, end: bool = False):
    if not value:
        return None
    if len(value) == 10:
        return f"{value}T{'23:59:59' if end else '00:00:00'}Z"
    return value


def _month_bounds(value: str):
    try:
        year, month = (int(part) for part in value.split("-"))
        last_day = calendar.monthrange(year, month)[1]
    except (TypeError, ValueError):
        return None, None
    return f"{year:04d}-{month:02d}-01T00:00:00Z", f"{year:04d}-{month:02d}-{last_day:02d}T23:59:59Z"


@router.get("/", response_class=HTMLResponse)
async def ui_home(request: Request):
    conn = db(request)
    month_value = request.query_params.get("month") or ""
    from_value = request.query_params.get("from") or ""
    to_value = request.query_params.get("to") or ""
    month_from, month_to = _month_bounds(month_value)
    from_bound = _dashboard_bound(from_value) if from_value else month_from
    to_bound = _dashboard_bound(to_value, end=True) if to_value else month_to
    accounts = await list_accounts_with_balance(conn)
    period_transactions = await list_transactions(conn, from_=from_bound, to=to_bound)
    recent = period_transactions[:5]
    report = await expenses_by_category(conn, from_bound, to_bound)
    account_names = {account["id"]: account["name"] for account in accounts}
    total_balance = sum(account["balance"] for account in accounts)
    total_income = sum(tx["amount"] for tx in period_transactions if tx["type"] == "income")
    total_expense = sum(tx["amount"] for tx in period_transactions if tx["type"] == "expense")
    return jinja_env.get_template("home.html").render(
        accounts=accounts,
        recent_transactions=recent,
        report=report,
        account_names=account_names,
        total_balance=total_balance,
        total_income=total_income,
        total_expense=total_expense,
        net_change=total_income - total_expense,
        month_value=month_value,
        from_value=from_value,
        to_value=to_value,
    )


@router.get("/ui/accounts", response_class=HTMLResponse)
async def ui_list_accounts(request: Request):
    conn = db(request)
    accounts = await list_accounts_with_balance(conn)
    return jinja_env.get_template("accounts_list.html").render(
        accounts=accounts, error=None, form_name="", form_type="cash"
    )


@router.post("/ui/accounts", response_class=HTMLResponse)
async def ui_create_account(request: Request):
    form = await request.form()
    name = (form.get("name") or "").strip()
    type_ = form.get("type") or ""

    error = None
    try:
        payload = AccountCreate(name=name, type=type_)
        await create_account(payload, request)
    except ValidationError:
        error = "Name and type are required"
    except HTTPException as exc:
        error = exc.detail
    else:
        return RedirectResponse("/ui/accounts", status_code=303)

    conn = db(request)
    accounts = await list_accounts_with_balance(conn)
    return jinja_env.get_template("accounts_list.html").render(
        accounts=accounts, error=error, form_name=name, form_type=type_ or "cash"
    )


@router.get("/ui/reports/expenses-by-category", response_class=HTMLResponse)
async def ui_expenses_by_category(request: Request):
    conn = db(request)
    from_value = request.query_params.get("from") or ""
    to_value = request.query_params.get("to") or ""
    report = await expenses_by_category(conn, from_value or None, to_value or None)
    return jinja_env.get_template("expenses_by_category.html").render(
        report=report, from_value=from_value, to_value=to_value
    )


@router.get("/ui/accounts/{account_id}/edit", response_class=HTMLResponse)
async def ui_edit_account_form(account_id: int, request: Request):
    conn = db(request)
    account = await fetch_account(conn, account_id)
    if account is None:
        return RedirectResponse("/ui/accounts", status_code=303)
    return jinja_env.get_template("account_edit.html").render(
        account=account, error=None
    )


@router.post("/ui/accounts/{account_id}/edit", response_class=HTMLResponse)
async def ui_update_account(account_id: int, request: Request):
    form = await request.form()
    name = (form.get("name") or "").strip()
    type_ = form.get("type") or ""

    error = None
    try:
        payload = AccountUpdate(name=name, type=type_)
        await update_account(account_id, payload, request)
    except ValidationError:
        error = "Name and type are required"
    except HTTPException as exc:
        if exc.status_code == 404:
            return RedirectResponse("/ui/accounts", status_code=303)
        error = exc.detail
    else:
        return RedirectResponse("/ui/accounts", status_code=303)

    account = {"id": account_id, "name": name, "type": type_, "created_at": ""}
    return jinja_env.get_template("account_edit.html").render(
        account=account, error=error
    )


@router.post("/ui/accounts/{account_id}/delete")
async def ui_delete_account(account_id: int, request: Request):
    try:
        await delete_account(account_id, request)
    except HTTPException:
        pass
    return RedirectResponse("/ui/accounts", status_code=303)


@router.get("/ui/categories", response_class=HTMLResponse)
async def ui_list_categories(request: Request):
    conn = db(request)
    result = await conn.prepare("SELECT id, name, type, created_at FROM categories ORDER BY id").all()
    return jinja_env.get_template("categories_list.html").render(
        categories=result.results, error=None, form_name="", form_type="expense"
    )


@router.post("/ui/categories", response_class=HTMLResponse)
async def ui_create_category(request: Request):
    form = await request.form()
    name = (form.get("name") or "").strip()
    type_ = form.get("type") or "expense"

    error = None
    try:
        payload = CategoryCreate(name=name, type=type_)
        await create_category(payload, request)
    except ValidationError:
        error = "Name and type are required"
    except HTTPException as exc:
        error = exc.detail
    else:
        return RedirectResponse("/ui/categories", status_code=303)

    conn = db(request)
    result = await conn.prepare("SELECT id, name, type, created_at FROM categories ORDER BY id").all()
    return jinja_env.get_template("categories_list.html").render(
        categories=result.results, error=error, form_name=name, form_type=type_
    )


@router.get("/ui/categories/{category_id}/edit", response_class=HTMLResponse)
async def ui_edit_category_form(category_id: int, request: Request):
    conn = db(request)
    category = await fetch_category(conn, category_id)
    if category is None:
        return RedirectResponse("/ui/categories", status_code=303)
    return jinja_env.get_template("category_edit.html").render(category=category, error=None)


@router.post("/ui/categories/{category_id}/edit", response_class=HTMLResponse)
async def ui_update_category(category_id: int, request: Request):
    form = await request.form()
    name = (form.get("name") or "").strip()

    error = None
    try:
        payload = CategoryUpdate(name=name)
        await update_category(category_id, payload, request)
    except ValidationError:
        error = "Name is required"
    except HTTPException as exc:
        if exc.status_code == 404:
            return RedirectResponse("/ui/categories", status_code=303)
        error = exc.detail
    else:
        return RedirectResponse("/ui/categories", status_code=303)

    category = {"id": category_id, "name": name, "created_at": ""}
    return jinja_env.get_template("category_edit.html").render(category=category, error=error)


@router.post("/ui/categories/{category_id}/delete")
async def ui_delete_category(category_id: int, request: Request):
    try:
        await delete_category(category_id, request)
    except HTTPException:
        pass
    return RedirectResponse("/ui/categories", status_code=303)


@router.get("/ui/transactions", response_class=HTMLResponse)
async def ui_list_transactions(request: Request):
    conn = db(request)
    transactions = await list_transactions(conn)
    accounts = await conn.prepare("SELECT id, name FROM accounts ORDER BY id").all()
    categories = await conn.prepare("SELECT id, name, type FROM categories ORDER BY id").all()
    return jinja_env.get_template("transactions_list.html").render(
        transactions=transactions,
        accounts=accounts.results,
        categories=categories.results,
        error=None,
        form={
            "type": "income",
            "account_id": "",
            "related_account_id": "",
            "category_id": "",
            "amount": "",
            "description": "",
            "occurred_at": "",
        },
    )


@router.post("/ui/transactions", response_class=HTMLResponse)
async def ui_create_transaction(request: Request):
    form = await request.form()
    type_ = form.get("type") or "income"
    account_id = form.get("account_id") or ""
    related_account_id = form.get("related_account_id") or None
    category_id = form.get("category_id") or None
    amount = form.get("amount") or ""
    description = (form.get("description") or "").strip() or None
    occurred_at = (form.get("occurred_at") or "").strip() or None

    error = None
    try:
        payload = TransactionCreate(
            type=type_,
            account_id=account_id,
            related_account_id=related_account_id,
            category_id=category_id,
            amount=amount,
            description=description,
            occurred_at=occurred_at,
        )
        if type_ == "transfer":
            await create_transfer(payload, request)
        else:
            await create_transaction(payload, request)
    except ValidationError:
        error = "Type, account, and positive amount are required"
    except HTTPException as exc:
        error = exc.detail
    else:
        return RedirectResponse("/ui/transactions", status_code=303)

    conn = db(request)
    transactions = await list_transactions(conn)
    accounts = await conn.prepare("SELECT id, name FROM accounts ORDER BY id").all()
    categories = await conn.prepare("SELECT id, name, type FROM categories ORDER BY id").all()
    return jinja_env.get_template("transactions_list.html").render(
        transactions=transactions,
        accounts=accounts.results,
        categories=categories.results,
        error=error,
        form={
            "type": type_,
            "account_id": account_id,
            "related_account_id": related_account_id or "",
            "category_id": category_id or "",
            "amount": amount,
            "description": description or "",
            "occurred_at": occurred_at or "",
        },
    )


@router.get("/ui/transactions/{transaction_id}/edit", response_class=HTMLResponse)
async def ui_edit_transaction_form(transaction_id: int, request: Request):
    conn = db(request)
    transaction = await fetch_transaction(conn, transaction_id)
    if transaction is None:
        return RedirectResponse("/ui/transactions", status_code=303)
    accounts = await conn.prepare("SELECT id, name FROM accounts ORDER BY id").all()
    categories = await conn.prepare("SELECT id, name, type FROM categories ORDER BY id").all()
    return jinja_env.get_template("transaction_edit.html").render(
        transaction=transaction,
        accounts=accounts.results,
        categories=categories.results,
        error=None,
    )


@router.post("/ui/transactions/{transaction_id}/edit", response_class=HTMLResponse)
async def ui_update_transaction(transaction_id: int, request: Request):
    form = await request.form()
    amount = form.get("amount") or ""
    category_id = form.get("category_id") or None
    description = (form.get("description") or "").strip() or None
    occurred_at = (form.get("occurred_at") or "").strip() or None

    error = None
    try:
        payload = TransactionUpdate(
            amount=amount,
            category_id=category_id,
            description=description,
            occurred_at=occurred_at,
        )
        await update_transaction(transaction_id, payload, request)
    except ValidationError:
        error = "Positive amount is required"
    except HTTPException as exc:
        if exc.status_code == 404:
            return RedirectResponse("/ui/transactions", status_code=303)
        error = exc.detail
    else:
        return RedirectResponse("/ui/transactions", status_code=303)

    conn = db(request)
    transaction = await fetch_transaction(conn, transaction_id)
    if transaction is None:
        return RedirectResponse("/ui/transactions", status_code=303)
    accounts = await conn.prepare("SELECT id, name FROM accounts ORDER BY id").all()
    categories = await conn.prepare("SELECT id, name, type FROM categories ORDER BY id").all()
    return jinja_env.get_template("transaction_edit.html").render(
        transaction={
            **transaction,
            "amount": amount,
            "category_id": category_id or transaction["category_id"],
            "description": description,
            "occurred_at": occurred_at or transaction["occurred_at"],
        },
        accounts=accounts.results,
        categories=categories.results,
        error=error,
    )


@router.post("/ui/transactions/{transaction_id}/delete")
async def ui_delete_transaction(transaction_id: int, request: Request):
    try:
        await delete_transaction(transaction_id, request)
    except HTTPException:
        pass
    return RedirectResponse("/ui/transactions", status_code=303)
