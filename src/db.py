from typing import Optional

from fastapi import Request


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


async def fetch_category(conn, category_id: int):
    row = (
        await conn.prepare("SELECT id, name, created_at FROM categories WHERE id = ?")
        .bind(category_id)
        .first()
    )
    return row


async def category_name_taken(conn, name: str, exclude_id: Optional[int] = None) -> bool:
    if exclude_id is None:
        row = await conn.prepare("SELECT id FROM categories WHERE name = ?").bind(name).first()
    else:
        row = (
            await conn.prepare("SELECT id FROM categories WHERE name = ? AND id != ?")
            .bind(name, exclude_id)
            .first()
        )
    return row is not None


async def fetch_transaction(conn, transaction_id: int):
    row = (
        await conn.prepare(
            "SELECT id, type, account_id, category_id, related_account_id, amount, description, occurred_at, created_at FROM transactions WHERE id = ?"
        )
        .bind(transaction_id)
        .first()
    )
    return row


async def account_exists(conn, account_id: int) -> bool:
    row = await conn.prepare("SELECT id FROM accounts WHERE id = ?").bind(account_id).first()
    return row is not None


async def category_exists(conn, category_id: int) -> bool:
    row = await conn.prepare("SELECT id FROM categories WHERE id = ?").bind(category_id).first()
    return row is not None


async def transaction_references_account(conn, account_id: int) -> bool:
    row = (
        await conn.prepare(
            "SELECT id FROM transactions WHERE account_id = ? OR related_account_id = ? LIMIT 1"
        )
        .bind(account_id, account_id)
        .first()
    )
    return row is not None


async def transaction_references_category(conn, category_id: int) -> bool:
    row = (
        await conn.prepare("SELECT id FROM transactions WHERE category_id = ? LIMIT 1")
        .bind(category_id)
        .first()
    )
    return row is not None


async def list_transactions(
    conn,
    account_id: Optional[int] = None,
    category_id: Optional[int] = None,
    type_: Optional[str] = None,
    from_: Optional[str] = None,
    to: Optional[str] = None,
):
    sql = (
        "SELECT id, type, account_id, category_id, related_account_id, amount, description, occurred_at, created_at FROM transactions"
    )
    clauses = []
    params = []

    if account_id is not None:
        clauses.append("account_id = ?")
        params.append(account_id)
    if category_id is not None:
        clauses.append("category_id = ?")
        params.append(category_id)
    if type_ is not None:
        clauses.append("type = ?")
        params.append(type_)
    if from_ is not None:
        clauses.append("occurred_at >= ?")
        params.append(from_)
    if to is not None:
        clauses.append("occurred_at <= ?")
        params.append(to)

    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY occurred_at DESC, id DESC"

    query = conn.prepare(sql)
    if params:
        query = query.bind(*params)
    result = await query.all()
    return result.results
