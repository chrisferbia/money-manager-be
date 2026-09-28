from datetime import datetime, timezone
from typing import Optional

from fastapi import Request


def db(request: Request):
    return request.scope["env"].money_manager


async def list_transaction_descriptions(conn, q: str = "", limit: int = 20):
    result = await (
        conn.prepare(
            """
            SELECT DISTINCT TRIM(description) AS description
            FROM transactions
            WHERE TRIM(description) <> ''
              AND INSTR(LOWER(TRIM(description)), LOWER(?)) > 0
            ORDER BY description COLLATE NOCASE, description
            LIMIT ?
            """
        )
        .bind(q.strip(), limit)
        .all()
    )
    return [row["description"] for row in result.results]


async def fetch_account(conn, account_id: int):
    row = (
        await conn.prepare(
            "SELECT id, name, type, sequence, valuation_mode, created_at FROM accounts WHERE id = ?"
        )
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
        await conn.prepare(
            "SELECT id, name, type, sequence, monthly_budget, created_at FROM categories WHERE id = ?"
        )
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


async def next_sequence(conn, table: str) -> int:
    if table not in {"accounts", "categories"}:
        raise ValueError("Unsupported sequence table")
    row = await conn.prepare(
        f"SELECT COALESCE(MAX(sequence), 0) + 1 AS sequence FROM {table}"
    ).first()
    return row["sequence"]


async def reorder(conn, table: str, item_id: int, requested_sequence: int):
    if table not in {"accounts", "categories"}:
        raise ValueError("Unsupported sequence table")

    rows = await conn.prepare(
        f"SELECT id FROM {table} ORDER BY sequence, id"
    ).all()
    ordered_ids = [row["id"] for row in rows.results if row["id"] != item_id]
    position = min(max(requested_sequence, 1), len(rows.results))
    ordered_ids.insert(position - 1, item_id)

    for sequence, row_id in enumerate(ordered_ids, start=1):
        await (
            conn.prepare(f"UPDATE {table} SET sequence = ? WHERE id = ?")
            .bind(sequence, row_id)
            .run()
        )


async def fetch_transaction(conn, transaction_id: int):
    row = (
        await conn.prepare(
            "SELECT id, type, account_id, category_id, related_account_id, amount, counterparty, description, occurred_at, created_at, transaction_subtype FROM transactions WHERE id = ?"
        )
        .bind(transaction_id)
        .first()
    )
    return row


async def insert_transaction(
    conn,
    type_: str,
    account_id: int,
    category_id: Optional[int],
    amount: int,
    counterparty: Optional[str],
    description: Optional[str],
    occurred_at: str,
    transaction_subtype: Optional[str] = None,
    source_message_id: Optional[str] = None,
):
    result = (
        await conn.prepare(
            "INSERT INTO transactions (type, account_id, category_id, related_account_id, amount, counterparty, description, occurred_at, transaction_subtype, source_message_id) VALUES (?, ?, ?, NULL, ?, ?, ?, ?, ?, ?)"
        )
        .bind(
            type_,
            account_id,
            category_id,
            amount,
            counterparty,
            description,
            occurred_at,
            transaction_subtype,
            source_message_id,
        )
        .run()
    )
    return result.meta.last_row_id


async def fetch_transaction_by_source_message_id(conn, source_message_id: str):
    return (
        await conn.prepare(
            "SELECT id, type, account_id, category_id, related_account_id, amount, counterparty, description, occurred_at, created_at, transaction_subtype FROM transactions WHERE source_message_id = ?"
        )
        .bind(source_message_id)
        .first()
    )


async def account_exists(conn, account_id: int) -> bool:
    row = await conn.prepare("SELECT id FROM accounts WHERE id = ?").bind(account_id).first()
    return row is not None


async def category_exists(conn, category_id: int) -> bool:
    row = await conn.prepare("SELECT id FROM categories WHERE id = ?").bind(category_id).first()
    return row is not None


async def category_matches_type(conn, category_id: int, type_: str) -> bool:
    row = (
        await conn.prepare("SELECT id FROM categories WHERE id = ? AND type = ?")
        .bind(category_id, type_)
        .first()
    )
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
        "SELECT id, type, account_id, category_id, related_account_id, amount, counterparty, description, occurred_at, created_at, transaction_subtype FROM transactions"
    )
    clauses = []
    params = []

    if account_id is not None:
        clauses.append("(account_id = ? OR related_account_id = ?)")
        params.append(account_id)
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


async def account_balance(conn, account_id: int):
    account = await fetch_account(conn, account_id)
    if account is not None and account["valuation_mode"] == "crypto":
        from crypto import crypto_account_value

        return await crypto_account_value(conn, account_id)
    row = (
        await conn.prepare(
            """
            SELECT COALESCE(SUM(
                CASE
                    WHEN type = 'income' AND account_id = ? THEN amount
                    WHEN type = 'expense' AND account_id = ? THEN -amount
                    WHEN type = 'transfer' AND account_id = ? THEN -amount
                    WHEN type = 'transfer' AND related_account_id = ? THEN amount
                    ELSE 0
                END
            ), 0) AS balance
            FROM transactions
            WHERE account_id = ? OR related_account_id = ?
            """
        )
        .bind(account_id, account_id, account_id, account_id, account_id, account_id)
        .first()
    )
    return 0 if row is None or row["balance"] is None else row["balance"]


def recent_month_keys(months: int = 12, now: Optional[datetime] = None):
    current = now or datetime.now(timezone.utc)
    month_index = current.year * 12 + current.month - 1
    keys = []
    for offset in range(months - 1, -1, -1):
        index = month_index - offset
        year, zero_based_month = divmod(index, 12)
        keys.append(f"{year:04d}-{zero_based_month + 1:02d}")
    return keys


def build_savings_balance_history(month_changes, month_keys):
    changes = {row["month"]: row["change"] or 0 for row in month_changes}
    first_month = month_keys[0]
    balance = sum(change for month, change in changes.items() if month < first_month)
    history = []
    for month in month_keys:
        change = changes.get(month, 0)
        balance += change
        history.append({"month": month, "balance": balance, "change": change})
    return history


async def savings_balance_history(conn, months: int = 12):
    account_row = await conn.prepare(
        "SELECT COUNT(*) AS count FROM accounts WHERE type = 'savings'"
    ).first()
    result = await conn.prepare(
        """
        SELECT
            SUBSTR(t.occurred_at, 1, 7) AS month,
            COALESCE(SUM(
                CASE
                    WHEN source.type = 'savings' AND t.type = 'income' THEN t.amount
                    WHEN source.type = 'savings' AND t.type IN ('expense', 'transfer') THEN -t.amount
                    ELSE 0
                END
                + CASE
                    WHEN destination.type = 'savings' AND t.type = 'transfer' THEN t.amount
                    ELSE 0
                END
            ), 0) AS change
        FROM transactions t
        LEFT JOIN accounts source ON source.id = t.account_id
        LEFT JOIN accounts destination ON destination.id = t.related_account_id
        WHERE source.type = 'savings' OR destination.type = 'savings'
        GROUP BY SUBSTR(t.occurred_at, 1, 7)
        ORDER BY month
        """
    ).all()
    month_keys = recent_month_keys(months)
    return {
        "account_count": 0 if account_row is None else account_row["count"],
        "months": build_savings_balance_history(result.results, month_keys),
    }


async def list_accounts_with_balance(conn):
    rows = await conn.prepare(
        "SELECT id, name, type, sequence, valuation_mode, created_at FROM accounts ORDER BY sequence, id"
    ).all()
    accounts = []
    for account in rows.results:
        balance = await account_balance(conn, account["id"])
        accounts.append({**account, "balance": balance})
    return accounts


async def expenses_by_category(conn, from_: Optional[str] = None, to: Optional[str] = None):
    sql = """
        SELECT c.id, c.name, COALESCE(SUM(t.amount), 0) AS total
        FROM categories c
        JOIN transactions t ON t.category_id = c.id
        WHERE t.type = 'expense'
    """
    params = []
    if from_ is not None:
        sql += " AND t.occurred_at >= ?"
        params.append(from_)
    if to is not None:
        sql += " AND t.occurred_at <= ?"
        params.append(to)
    sql += " GROUP BY c.id, c.name HAVING COALESCE(SUM(t.amount), 0) > 0 ORDER BY total DESC, c.name ASC"

    query = conn.prepare(sql)
    if params:
        query = query.bind(*params)
    result = await query.all()
    return result.results


async def recent_transactions(conn, limit: int = 5):
    result = await conn.prepare(
        "SELECT id, type, account_id, category_id, related_account_id, amount, counterparty, description, occurred_at, created_at, transaction_subtype FROM transactions ORDER BY occurred_at DESC, id DESC LIMIT ?"
    ).bind(limit).all()
    return result.results
