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
