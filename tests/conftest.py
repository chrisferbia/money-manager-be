import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

import pytest

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
def initialize_local_db():
    """Create the local D1 schema once for the test session."""
    subprocess.run(
        [
            "npx.cmd",
            "--yes",
            "wrangler",
            "d1",
            "execute",
            D1_DATABASE_NAME,
            "--local",
            "--file",
            "db_init.sql",
        ],
        cwd=REPO_ROOT,
        check=True,
    )


@contextmanager
def pywrangler_dev_server():
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
            "--var",
            "TEST_MODE:true",
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

    database, client = create_client(app, (REPO_ROOT / "db_init.sql").read_text())
    with client:
        yield database, client


@pytest.fixture(scope="session")
def worker_server(initialize_local_db):
    """Yield one real Worker's port for explicit Worker smoke tests."""
    with pywrangler_dev_server() as port:
        yield port


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
