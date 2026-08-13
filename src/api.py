from fastapi import APIRouter, HTTPException, Request

from db import (
    account_name_taken,
    category_name_taken,
    db,
    fetch_account,
    fetch_category,
)
from models import (
    Account,
    AccountCreate,
    AccountUpdate,
    Category,
    CategoryCreate,
    CategoryUpdate,
)

router = APIRouter()


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


@router.get("/accounts", response_model=list[Account])
async def list_accounts(request: Request):
    conn = db(request)
    result = await conn.prepare("SELECT id, name, type, created_at FROM accounts ORDER BY id").all()
    return result.results


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
    await conn.prepare("DELETE FROM categories WHERE id = ?").bind(category_id).run()
