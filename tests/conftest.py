import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parents[1]
D1_DATABASE_NAME = "money-manager"


def find_free_port():
    """Find an unused port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        port = s.getsockname()[1]
    return port


def reset_local_db():
    """Apply db_init.sql then clear leftover rows so each test run starts clean."""
    subprocess.run(
        [
            "uv",
            "run",
            "pywrangler",
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
    subprocess.run(
        [
            "uv",
            "run",
            "pywrangler",
            "d1",
            "execute",
            D1_DATABASE_NAME,
            "--local",
            "--command",
            "DELETE FROM accounts;",
        ],
        cwd=REPO_ROOT,
        check=True,
    )


@contextmanager
def pywrangler_dev_server():
    """Context manager to start and stop the pywrangler dev server."""
    port = find_free_port()

    process = subprocess.Popen(
        ["uv", "run", "pywrangler", "dev", "--port", str(port)],
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


@pytest.fixture(scope="module")
def dev_server():
    """Resets the local D1 accounts table, then yields a running Worker's port."""
    reset_local_db()
    with pywrangler_dev_server() as port:
        yield port
