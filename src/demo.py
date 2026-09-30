"""Explicit, read-only public access to the reserved fictional demo workspace."""

from fastapi import APIRouter, Depends, HTTPException, Request

import api


router = APIRouter(prefix="/demo")


async def require_demo_workspace(request: Request) -> int:
    row = await request.scope["env"].money_manager.prepare(
        "SELECT id FROM workspaces WHERE id = 1 AND owner_user_id IS NULL"
    ).first()
    if row is None:
        raise HTTPException(status_code=503, detail="Demo is unavailable")
    request.state.workspace_id = row["id"]
    return row["id"]


@router.get("/metadata", dependencies=[Depends(require_demo_workspace)])
async def demo_metadata(request: Request):
    row = await request.scope["env"].money_manager.prepare(
        "SELECT MAX(occurred_at) AS latest_transaction_at FROM transactions WHERE workspace_id = 1"
    ).first()
    return {"latest_transaction_at": row["latest_transaction_at"] if row else None}


# Deliberately enumerate public routes. Private routes, writes, email imports,
# and free-form account/transaction lookups are never exposed by this router.
for path, endpoint in (
    ("/accounts", api.list_accounts),
    ("/categories", api.list_categories),
    ("/transactions", api.list_transaction_route),
    ("/reports/expenses-by-category", api.report_expenses_by_category),
    ("/reports/savings-balance-history", api.report_savings_balance_history),
    ("/accounts/{account_id}/holdings", api.list_crypto_holdings),
):
    router.add_api_route(path, endpoint, methods=["GET"], dependencies=[Depends(require_demo_workspace)])
