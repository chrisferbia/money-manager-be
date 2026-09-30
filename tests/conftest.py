import socket
import subprocess
import sys
import time
import json
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from fake_d1 import InProcessRequests, create_client

REPO_ROOT = Path(__file__).parents[1]
D1_DATABASE_NAME = "money-manager"


def find_free_port():
    """Find an unused port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        port = s.getsockname()[1]
    return port


@pytest.fixture(scope="session")
def initialize_local_db(tmp_path_factory):
    """Create an isolated local D1 schema for Worker smoke tests."""
    configuration = json.loads((REPO_ROOT / "wrangler.jsonc").read_text())
    if configuration["d1_databases"][0].get("remote") is not False:
        pytest.skip("Worker smoke tests require the default D1 binding to be local")
    persist_path = tmp_path_factory.mktemp("worker-d1")
    subprocess.run(
        [
            "npx.cmd",
            "--yes",
            "wrangler",
            "d1",
            "execute",
            D1_DATABASE_NAME,
            "--local",
            "--persist-to",
            str(persist_path),
            "--file",
            "db_init.sql",
        ],
        cwd=REPO_ROOT,
        check=True,
    )
    return persist_path


@contextmanager
def pywrangler_dev_server(persist_path, public_key):
    """Context manager to start and stop the pywrangler dev server."""
    port = find_free_port()

    process = subprocess.Popen(
        [
            "uv",
            "run",
            "pywrangler",
            "dev",
            "--port",
            str(port),
            "--persist-to",
            str(persist_path),
            "--var",
            "CLERK_ISSUER:https://test.clerk.example",
            "--var",
            "CLERK_AUTHORIZED_PARTIES:http://localhost:5173",
            "--var",
            "CLERK_JWT_KEY:" + public_key.replace("\n", "\\n"),
        ],
        cwd=REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    ready = False
    timeout = 60
    start_time = time.time()

    while not ready and time.time() - start_time < timeout:
        line = process.stdout.readline()
        if line:
            print(line.rstrip(), file=sys.stdout)
            if "[wrangler:info] Ready on" in line:
                ready = True
                break
        time.sleep(0.1)

    if not ready:
        process.terminate()
        raise RuntimeError(f"Server failed to start within {timeout} seconds")

    try:
        yield port
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()


@pytest.fixture(scope="session")
def inprocess_app():
    from app import app
    from auth import require_workspace
    from fastapi import Request

    async def demo_workspace(request: Request):
        request.state.workspace_id = int(request.headers.get("X-Test-Workspace", "1"))
        return request.state.workspace_id

    app.dependency_overrides[require_workspace] = demo_workspace

    database, client = create_client(app, (REPO_ROOT / "db_init.sql").read_text())
    with client:
        yield database, client
    app.dependency_overrides.clear()


@pytest.fixture(scope="session")
def worker_server(initialize_local_db):
    """Yield one real local Worker and a test-only Clerk session issuer."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode()

    def token(subject):
        now = datetime.now(timezone.utc)
        return jwt.encode(
            {
                "sub": subject,
                "iss": "https://test.clerk.example",
                "azp": "http://localhost:5173",
                "iat": int(now.timestamp()),
                "exp": int((now + timedelta(minutes=10)).timestamp()),
            },
            private_key,
            algorithm="RS256",
        )

    with pywrangler_dev_server(initialize_local_db, public_key) as port:
        yield port, token


@pytest.fixture(scope="session")
def dev_server(inprocess_app):
    """Provide a compatibility port while tests run in-process."""
    yield 0


@pytest.fixture(autouse=True)
def clean_local_db(request):
    """Reset the in-memory D1 and route HTTP calls through TestClient."""
    if not request.node.get_closest_marker("integration"):
        return

    database, client = request.getfixturevalue("inprocess_app")
    request.module.requests = InProcessRequests(client)
    database.reset()
