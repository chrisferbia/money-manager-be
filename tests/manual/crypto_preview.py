"""Loopback-only crypto UI verification with fictional, in-memory data.

Run from the backend root: python tests/manual/crypto_preview.py
Never deploy this adapter. It uses no real D1, credentials, or market API.
"""
from datetime import datetime, timezone
from pathlib import Path
import sys

import uvicorn
from fastapi import Request
from fastapi.middleware.cors import CORSMiddleware

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from app import app
from auth import require_workspace
import crypto
from fake_d1 import FakeD1, InProcessApp


async def preview_workspace(request: Request):
    request.state.workspace_id = 1
    return 1


async def fictional_market(path, env):
    return {"bitcoin": {"idr": 1200000000, "last_updated_at": int(datetime.now(timezone.utc).timestamp())}}


if __name__ == "__main__":
    database = FakeD1((ROOT / "db_init.sql").read_text())
    database.reset()
    database.connection.executescript("""
        INSERT INTO accounts (id,workspace_id,name,type,valuation_mode) VALUES (1,1,'Fictional crypto wallet','investment','crypto');
        INSERT INTO categories (id,workspace_id,name,type) VALUES (1,1,'Other','expense');
        INSERT INTO crypto_holdings (id,workspace_id,account_id,coin_id,name,symbol,quantity) VALUES (1,1,1,'bitcoin','Bitcoin','BTC','0.01');
    """)
    database.connection.execute(
        "INSERT INTO crypto_prices (coin_id,price_idr,fetched_at) VALUES ('bitcoin','1000000000',?)",
        (datetime.now(timezone.utc).isoformat(),),
    )
    database.connection.commit()
    app.dependency_overrides[require_workspace] = preview_workspace
    crypto._fetch_market_json = fictional_market
    preview = CORSMiddleware(InProcessApp(app, database), allow_origins=["http://127.0.0.1:5179"], allow_methods=["*"], allow_headers=["*"])
    uvicorn.run(preview, host="127.0.0.1", port=8791)
