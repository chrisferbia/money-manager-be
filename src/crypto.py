"""Crypto holdings and CoinGecko IDR market prices."""

import json
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from urllib.parse import urlencode

PRICE_TTL_SECONDS = 600
MARKET_USER_AGENT = "MoneyManager/1.0 (personal finance crypto holdings and IDR valuation)"
COIN_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,99}$")
QUANTITY_RE = re.compile(r"^(?:0|[1-9]\d{0,11})(?:\.\d{1,18})?$")


def normalize_quantity(value: str) -> str:
    if not QUANTITY_RE.fullmatch(value):
        raise ValueError("Quantity must be a positive decimal with at most 18 places")
    try:
        quantity = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("Invalid quantity") from exc
    if quantity <= 0:
        raise ValueError("Quantity must be greater than zero")
    return format(quantity.normalize(), "f")


def value_idr(quantity: str, price_idr: str) -> int:
    return int((Decimal(quantity) * Decimal(price_idr)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _is_fresh(fetched_at: str | None, now: datetime) -> bool:
    if not fetched_at:
        return False
    try:
        fetched = datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))
        return 0 <= (now - fetched).total_seconds() < PRICE_TTL_SECONDS
    except ValueError:
        return False


def market_headers(env):
    headers = {"Accept": "application/json", "User-Agent": MARKET_USER_AGENT}
    key = getattr(env, "COINGECKO_API_KEY", None)
    if key:
        headers["x-cg-demo-api-key"] = key
    return headers


async def _fetch_market_json(path: str, env):
    # Import inside the Worker-only boundary so in-process tests can inject a provider.
    from js import Object, fetch
    from pyodide.ffi import to_js

    response = await fetch(
        f"https://api.coingecko.com/api/v3/{path}",
        to_js({"headers": market_headers(env)}, dict_converter=Object.fromEntries),
    )
    if not response.ok:
        body = await response.text()
        raise RuntimeError(f"CoinGecko returned HTTP {response.status}: {body[:300]}")
    return json.loads(await response.text())


async def search_coins(query: str, env):
    data = await _fetch_market_json(f"search?{urlencode({'query': query})}", env)
    coins = data.get("coins", [])
    return [
        {"coin_id": coin["id"], "name": coin["name"], "symbol": coin["symbol"].upper()}
        for coin in coins[:20]
        if isinstance(coin, dict)
        and COIN_ID_RE.fullmatch(str(coin.get("id", "")))
        and coin.get("name")
        and coin.get("symbol")
    ]


async def refresh_prices(conn, env, coin_ids: list[str]):
    if not coin_ids:
        return
    now = datetime.now(timezone.utc)
    cached = await conn.prepare("SELECT coin_id, fetched_at FROM crypto_prices").all()
    fetched_at = {row["coin_id"]: row["fetched_at"] for row in cached.results}
    stale = sorted({coin_id for coin_id in coin_ids if not _is_fresh(fetched_at.get(coin_id), now)})
    for start in range(0, len(stale), 100):
        batch = stale[start : start + 100]
        try:
            data = await _fetch_market_json(
                f"simple/price?{urlencode({'ids': ','.join(batch), 'vs_currencies': 'idr', 'include_last_updated_at': 'true'})}",
                env,
            )
        except Exception:
            # Keep the last known price; callers distinguish stale and missing prices.
            continue
        if not isinstance(data, dict):
            continue
        for coin_id in batch:
            quote = data.get(coin_id, {})
            if not isinstance(quote, dict):
                continue
            try:
                price = Decimal(str(quote.get("idr")))
            except InvalidOperation:
                continue
            if not price.is_finite() or price <= 0:
                continue
            provider_time = quote.get("last_updated_at")
            provider_updated_at = (
                datetime.fromtimestamp(provider_time, timezone.utc).isoformat()
                if isinstance(provider_time, int) and provider_time > 0
                else None
            )
            await (
                conn.prepare(
                    "INSERT INTO crypto_prices (coin_id, price_idr, provider_updated_at, fetched_at) "
                    "VALUES (?, ?, ?, ?) ON CONFLICT(coin_id) DO UPDATE SET "
                    "price_idr = excluded.price_idr, provider_updated_at = excluded.provider_updated_at, "
                    "fetched_at = excluded.fetched_at"
                )
                .bind(coin_id, str(price), provider_updated_at, now.isoformat())
                .run()
            )


async def account_holdings(conn, account_id: int):
    result = await (
        conn.prepare(
            "SELECT h.id, h.account_id, h.coin_id, h.name, h.symbol, h.quantity, "
            "p.price_idr, p.provider_updated_at, p.fetched_at "
            "FROM crypto_holdings h LEFT JOIN crypto_prices p ON p.coin_id = h.coin_id "
            "WHERE h.workspace_id = ? AND h.account_id = ? ORDER BY h.name COLLATE NOCASE, h.id"
        )
        .bind(conn.workspace_id, account_id)
        .all()
    )
    now = datetime.now(timezone.utc)
    return [
        {
            **row,
            "value_idr": value_idr(row["quantity"], row["price_idr"])
            if row["price_idr"] is not None
            else None,
            "price_status": "fresh" if _is_fresh(row["fetched_at"], now) else (
                "stale" if row["price_idr"] is not None else "unavailable"
            ),
        }
        for row in result.results
    ]


async def crypto_account_value(conn, account_id: int):
    holdings = await account_holdings(conn, account_id)
    if any(holding["value_idr"] is None for holding in holdings):
        return None
    # Round the combined value once, rather than rounding every tiny holding first.
    total = sum(
        (Decimal(row["quantity"]) * Decimal(row["price_idr"]) for row in holdings),
        Decimal(0),
    )
    return int(total.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
