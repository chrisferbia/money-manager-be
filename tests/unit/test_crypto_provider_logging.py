"""Exercise the Worker fetch boundary without real network or credentials."""
import asyncio
import json
import sys
from types import SimpleNamespace

import pytest

import crypto

pytestmark = pytest.mark.unit


def mock_worker_fetch(monkeypatch, status, body):
    async def text():
        return body
    async def fetch(url, options):
        return SimpleNamespace(ok=200 <= status < 300, status=status, text=text)
    monkeypatch.setitem(sys.modules, "js", SimpleNamespace(
        Object=SimpleNamespace(fromEntries=object()), fetch=fetch,
    ))
    monkeypatch.setitem(sys.modules, "pyodide.ffi", SimpleNamespace(
        to_js=lambda value, **kwargs: value,
    ))


@pytest.mark.parametrize("status,code", [(429, None), (403, None), (401, 10010)])
def test_http_error_preserves_only_status_and_safe_provider_code(monkeypatch, status, code):
    secret = "fictional-private-api-key"
    body = json.dumps({"status": {"error_code": code, "error_message": secret}, "request": secret})
    mock_worker_fetch(monkeypatch, status, body)
    with pytest.raises(crypto.MarketProviderError) as result:
        asyncio.run(crypto._fetch_market_json("simple/price?ids=private-held-coin", SimpleNamespace(COINGECKO_API_KEY=secret)))
    assert result.value.reason == "http_error"
    assert result.value.http_status == status
    assert result.value.provider_code == code
    assert secret not in str(result.value)
    assert "private-held-coin" not in str(result.value)


def test_non_json_error_response_does_not_expose_body(monkeypatch):
    mock_worker_fetch(monkeypatch, 403, "<html>private-api-key and request data</html>")
    with pytest.raises(crypto.MarketProviderError) as result:
        asyncio.run(crypto._fetch_market_json("simple/price", SimpleNamespace()))
    assert result.value.http_status == 403
    assert result.value.provider_code is None
    assert "private-api-key" not in str(result.value)


def test_invalid_json_response_has_safe_diagnostic(monkeypatch):
    mock_worker_fetch(monkeypatch, 200, "invalid response containing private-api-key")
    with pytest.raises(crypto.MarketProviderError) as result:
        asyncio.run(crypto._fetch_market_json("simple/price", SimpleNamespace()))
    assert result.value.reason == "invalid_json"
    assert result.value.http_status == 200
    assert "private-api-key" not in str(result.value)


def test_successful_response_is_unchanged(monkeypatch):
    mock_worker_fetch(monkeypatch, 200, '{"bitcoin":{"idr":1000}}')
    assert asyncio.run(crypto._fetch_market_json("simple/price", SimpleNamespace())) == {"bitcoin": {"idr": 1000}}


@pytest.mark.parametrize("body", [
    "not JSON", "[]", '{"status":null}', '{"status":{"error_code":true}}',
    '{"error_code":"secret"}', '{"status":{"error_code":-1}}',
    '{"status":{"error_code":1000000}}',
])
def test_provider_code_extraction_rejects_untrusted_values(body):
    assert crypto._provider_error_code(body) is None
