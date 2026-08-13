import jinja2
import templates
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError

from api import create_account, create_category, delete_account, delete_category, update_account, update_category
from db import db, fetch_account, fetch_category
from models import AccountCreate, AccountUpdate, CategoryCreate, CategoryUpdate

router = APIRouter()

jinja_env = jinja2.Environment(
    loader=jinja2.DictLoader(templates.TEMPLATES), autoescape=True
)


@router.get("/ui/accounts", response_class=HTMLResponse)
async def ui_list_accounts(request: Request):
    conn = db(request)
    result = await conn.prepare(
        "SELECT id, name, type, created_at FROM accounts ORDER BY id"
    ).all()
    return jinja_env.get_template("accounts_list.html").render(
        accounts=result.results, error=None, form_name="", form_type="cash"
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
    result = await conn.prepare(
        "SELECT id, name, type, created_at FROM accounts ORDER BY id"
    ).all()
    return jinja_env.get_template("accounts_list.html").render(
        accounts=result.results, error=error, form_name=name, form_type=type_ or "cash"
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
    result = await conn.prepare("SELECT id, name, created_at FROM categories ORDER BY id").all()
    return jinja_env.get_template("categories_list.html").render(
        categories=result.results, error=None, form_name=""
    )


@router.post("/ui/categories", response_class=HTMLResponse)
async def ui_create_category(request: Request):
    form = await request.form()
    name = (form.get("name") or "").strip()

    error = None
    try:
        payload = CategoryCreate(name=name)
        await create_category(payload, request)
    except ValidationError:
        error = "Name is required"
    except HTTPException as exc:
        error = exc.detail
    else:
        return RedirectResponse("/ui/categories", status_code=303)

    conn = db(request)
    result = await conn.prepare("SELECT id, name, created_at FROM categories ORDER BY id").all()
    return jinja_env.get_template("categories_list.html").render(
        categories=result.results, error=error, form_name=name
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
