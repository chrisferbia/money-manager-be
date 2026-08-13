import jinja2
import templates
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError

from api import create_account, delete_account, update_account
from db import db, fetch_account
from models import AccountCreate, AccountUpdate

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
