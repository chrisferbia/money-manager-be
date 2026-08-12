from typing import Optional

import jinja2
import templates
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field, ValidationError
from workers import WorkerEntrypoint

jinja_env = jinja2.Environment(
    loader=jinja2.DictLoader(templates.TEMPLATES), autoescape=True
)


class AccountCreate(BaseModel):
    name: str = Field(min_length=1)
    type: str = Field(min_length=1)


class AccountUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1)
    type: Optional[str] = Field(default=None, min_length=1)


class Account(BaseModel):
    id: int
    name: str
    type: str
    created_at: str


app = FastAPI()


def db(request: Request):
    return request.scope["env"].money_manager


async def fetch_account(conn, account_id: int):
    row = (
        await conn.prepare("SELECT id, name, type, created_at FROM accounts WHERE id = ?")
        .bind(account_id)
        .first()
    )
    return row


async def account_name_taken(conn, name: str, exclude_id: Optional[int] = None) -> bool:
    if exclude_id is None:
        row = await conn.prepare("SELECT id FROM accounts WHERE name = ?").bind(name).first()
    else:
        row = (
            await conn.prepare("SELECT id FROM accounts WHERE name = ? AND id != ?")
            .bind(name, exclude_id)
            .first()
        )
    return row is not None


@app.post("/accounts", status_code=201, response_model=Account)
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


@app.get("/accounts", response_model=list[Account])
async def list_accounts(request: Request):
    conn = db(request)
    result = await conn.prepare("SELECT id, name, type, created_at FROM accounts ORDER BY id").all()
    return result.results


@app.get("/accounts/{account_id}", response_model=Account)
async def get_account(account_id: int, request: Request):
    conn = db(request)
    account = await fetch_account(conn, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    return account


@app.patch("/accounts/{account_id}", response_model=Account)
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


@app.delete("/accounts/{account_id}", status_code=204)
async def delete_account(account_id: int, request: Request):
    conn = db(request)
    existing = await fetch_account(conn, account_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Account not found")
    await conn.prepare("DELETE FROM accounts WHERE id = ?").bind(account_id).run()


@app.get("/ui/accounts", response_class=HTMLResponse)
async def ui_list_accounts(request: Request):
    conn = db(request)
    result = await conn.prepare(
        "SELECT id, name, type, created_at FROM accounts ORDER BY id"
    ).all()
    return jinja_env.get_template("accounts_list.html").render(
        accounts=result.results, error=None, form_name="", form_type="cash"
    )


@app.post("/ui/accounts", response_class=HTMLResponse)
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


@app.get("/ui/accounts/{account_id}/edit", response_class=HTMLResponse)
async def ui_edit_account_form(account_id: int, request: Request):
    conn = db(request)
    account = await fetch_account(conn, account_id)
    if account is None:
        return RedirectResponse("/ui/accounts", status_code=303)
    return jinja_env.get_template("account_edit.html").render(
        account=account, error=None
    )


@app.post("/ui/accounts/{account_id}/edit", response_class=HTMLResponse)
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


@app.post("/ui/accounts/{account_id}/delete")
async def ui_delete_account(account_id: int, request: Request):
    try:
        await delete_account(account_id, request)
    except HTTPException:
        pass
    return RedirectResponse("/ui/accounts", status_code=303)


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        import asgi

        return await asgi.fetch(app, request.js_object, self.env)
