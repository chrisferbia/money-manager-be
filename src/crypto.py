"""Crypto holdings and CoinGecko IDR market prices."""

import json
import logging
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from urllib.parse import urlencode

PRICE_TTL_SECONDS = 600
MARKET_USER_AGENT = "MoneyManager/1.0 (personal finance crypto holdings and IDR valuation)"
COIN_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,99}$")
QUANTITY_RE = re.compile(r"^(?:0|[1-9]\d{0,11})(?:\.\d{1,18})?$")
logger = logging.getLogger(__name__)


class MarketProviderError(RuntimeError):
    """Provider diagnostics without response bodies, URLs or credentials."""

    def __init__(self, reason: str, http_status: int, provider_code: int | None = None):
        self.reason = reason
        self.http_status = http_status
        self.provider_code = provider_code
        super().__init__(
            f"CoinGecko request failed: reason={reason} http_status={http_status} "
            f"provider_code={provider_code}"
        )


def _provider_error_code(body: str) -> int | None:
    # Only allow a numeric error code out of the untrusted provider response.
    try:
        data = json.loads(body)
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    status = data.get("status")
    code = status.get("error_code") if isinstance(status, dict) else data.get("error_code")
    return code if type(code) is int and 0 <= code <= 999999 else None


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


def _is_fresh(fetched_at: str | None, now: datetime, ttl_seconds: int = PRICE_TTL_SECONDS) -> bool:
    if not fetched_at:
        return False
    try:
        fetched = datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))
        return 0 <= (now - fetched).total_seconds() < ttl_seconds
    except (ValueError, TypeError):
        return False


async def price_ttl_seconds(conn) -> int:
    row = await conn.prepare(
        "SELECT crypto_price_expiry_minutes FROM workspaces WHERE id = ?"
    ).bind(conn.workspace_id).first()
    return row["crypto_price_expiry_minutes"] * 60 if row else PRICE_TTL_SECONDS


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
        try:
            provider_code = _provider_error_code(await response.text())
        except Exception:
            provider_code = None
        raise MarketProviderError("http_error", int(response.status), provider_code)
    try:
        return json.loads(await response.text())
    except (ValueError, TypeError):
        raise MarketProviderError("invalid_json", int(response.status)) from None


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


async def refresh_prices(conn, env, coin_ids: list[str], *, force: bool = False):
    """Reuse fresh quotes; only the manual-refresh endpoint may force a fetch."""
    if not coin_ids:
        return set()
    now = datetime.now(timezone.utc)
    ttl_seconds = await price_ttl_seconds(conn)
    cached = await conn.prepare("SELECT coin_id, fetched_at FROM crypto_prices").all()
    fetched_at = {row["coin_id"]: row["fetched_at"] for row in cached.results}
    stale = sorted({coin_id for coin_id in coin_ids if force or not _is_fresh(fetched_at.get(coin_id), now, ttl_seconds)})
    if not stale:
        # Page loads, polling and holding changes must not fetch fresh prices.
        return set()
    mode = "manual" if force else "automatic"
    key_configured = bool(getattr(env, "COINGECKO_API_KEY", None))
    refreshed = set()
    for start in range(0, len(stale), 100):
        batch = stale[start : start + 100]
        try:
            data = await _fetch_market_json(
                f"simple/price?{urlencode({'ids': ','.join(batch), 'vs_currencies': 'idr', 'include_last_updated_at': 'true'})}",
                env,
            )
        except Exception as exc:
            # Do not log exception text/tracebacks: these can contain request secrets.
            logger.warning(
                "Crypto price refresh failed: provider=coingecko mode=%s reason=%s "
                "http_status=%s provider_code=%s api_key_configured=%s exception_type=%s; "
                "cached prices kept",
                mode,
                exc.reason if isinstance(exc, MarketProviderError) else "transport_or_runtime_error",
                exc.http_status if isinstance(exc, MarketProviderError) else None,
                exc.provider_code if isinstance(exc, MarketProviderError) else None,
                key_configured,
                type(exc).__name__,
            )
            # Keep the last known price; callers distinguish stale and missing prices.
            continue
        if not isinstance(data, dict):
            logger.warning(
                "Crypto price refresh returned unusable data: provider=coingecko mode=%s "
                "reason=invalid_response_shape api_key_configured=%s; cached prices kept",
                mode, key_configured,
            )
            continue
        invalid_reasons = set()
        for coin_id in batch:
            if coin_id not in data:
                invalid_reasons.add("missing_quote")
                continue
            quote = data.get(coin_id, {})
            if not isinstance(quote, dict):
                invalid_reasons.add("invalid_quote_shape")
                continue
            try:
                price = Decimal(str(quote.get("idr")))
            except InvalidOperation:
                invalid_reasons.add("invalid_idr_price")
                continue
            if not price.is_finite() or price <= 0:
                invalid_reasons.add("invalid_idr_price")
                continue
            provider_time = quote.get("last_updated_at")
            try:
                provider_updated_at = (
                    datetime.fromtimestamp(provider_time, timezone.utc).isoformat()
                    if isinstance(provider_time, int) and provider_time > 0
                    else None
                )
            except (ValueError, OverflowError, OSError):
                invalid_reasons.add("invalid_provider_timestamp")
                continue
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
            refreshed.add(coin_id)
        if invalid_reasons:
            logger.warning(
                "Crypto price refresh returned unusable quotes: provider=coingecko mode=%s "
                "reason=%s api_key_configured=%s; cached prices kept for rejected quotes",
                mode, ",".join(sorted(invalid_reasons)), key_configured,
            )
    return refreshed


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
    ttl_seconds = await price_ttl_seconds(conn)
    return [
        {
            **row,
            "value_idr": value_idr(row["quantity"], row["price_idr"])
            if row["price_idr"] is not None
            else None,
            "price_status": "fresh" if _is_fresh(row["fetched_at"], now, ttl_seconds) else (
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
