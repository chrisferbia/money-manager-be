from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import asyncio

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException, Request

from auth import require_subject


pytestmark = pytest.mark.unit


def _request(token, public_key):
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/me",
        "headers": [(b"authorization", f"Bearer {token}".encode())],
        "env": SimpleNamespace(
            CLERK_JWT_KEY=public_key,
            CLERK_AUTHORIZED_PARTIES="http://localhost:5173,https://money-manager-fe.azamines.workers.dev",
            CLERK_ISSUER="https://topical-meerkat-6998.clerk.accounts.dev",
        ),
    }
    return Request(scope)


def test_session_signature_and_authorized_party_are_required():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_pem = private.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    now = datetime.now(timezone.utc)
    claims = {
        "sub": "user_alice",
        "iss": "https://topical-meerkat-6998.clerk.accounts.dev",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=1)).timestamp()),
        "nbf": int((now - timedelta(seconds=1)).timestamp()),
        "azp": "http://localhost:5173",
    }
    token = jwt.encode(claims, private, algorithm="RS256")
    assert asyncio.run(require_subject(_request(token, public_pem))) == "user_alice"

    with pytest.raises(HTTPException) as tampered:
        asyncio.run(require_subject(_request(token + "x", public_pem)))
    assert tampered.value.status_code == 401

    wrong_origin = jwt.encode({**claims, "azp": "https://evil.example"}, private, algorithm="RS256")
    with pytest.raises(HTTPException) as rejected:
        asyncio.run(require_subject(_request(wrong_origin, public_pem)))
    assert rejected.value.status_code == 401

    wrong_issuer = jwt.encode({**claims, "iss": "https://evil.example"}, private, algorithm="RS256")
    with pytest.raises(HTTPException) as rejected:
        asyncio.run(require_subject(_request(wrong_issuer, public_pem)))
    assert rejected.value.status_code == 401

    without_party = jwt.encode({key: value for key, value in claims.items() if key != "azp"}, private, algorithm="RS256")
    with pytest.raises(HTTPException) as rejected:
        asyncio.run(require_subject(_request(without_party, public_pem)))
    assert rejected.value.status_code == 401
