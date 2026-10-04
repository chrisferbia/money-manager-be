"""Exercise the real Python Worker and D1 batch using an explicitly local binding."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import socket
import subprocess
import time
import uuid

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import jwt
import requests

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "wrangler.import-review-test.jsonc"
PERSIST = ROOT / ".wrangler" / "import-review-tests"


def main():
    subprocess.run(["npx.cmd", "wrangler", "d1", "execute", "money-manager-import-review-test", "--config", str(CONFIG), "--local", "--persist-to", str(PERSIST), "--file", "db_init.sql"], cwd=ROOT, check=True)
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    now = datetime.now(timezone.utc)
    token = jwt.encode({"sub": "import-test-" + str(uuid.uuid4()), "iss": "https://test.clerk.example", "azp": "http://localhost:5173", "iat": now, "exp": now + timedelta(minutes=10)}, private_key, algorithm="RS256")
    headers = {"Authorization": "Bearer " + token}
    log_path = PERSIST / "worker-smoke.log"
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(["npx.cmd", "wrangler", "dev", "--config", str(CONFIG), "--ip", "127.0.0.1", "--port", str(port), "--persist-to", str(PERSIST), "--var", "CLERK_ISSUER:https://test.clerk.example", "--var", "CLERK_AUTHORIZED_PARTIES:http://localhost:5173", "--var", "CLERK_JWT_KEY:" + public_key.replace("\n", "\\n")], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
        base = f"http://127.0.0.1:{port}"
        try:
            ready = False
            for _ in range(120):
                if process.poll() is not None:
                    break
                try:
                    response = requests.get(base + "/imports", timeout=1)
                    if response.status_code == 401:
                        ready = True
                        break
                except requests.RequestException:
                    pass
                time.sleep(0.5)
            if not ready:
                raise RuntimeError("Local Worker failed to start: " + log_path.read_text(encoding="utf-8", errors="replace")[-4000:])
            print("Local Worker ready; verifying staged approval and D1 transaction", flush=True)
            def call(method, path, **kwargs):
                response = requests.request(method, base + path, headers=headers, timeout=20, **kwargs)
                assert response.ok, f"{path}: {response.status_code} {response.text}"
                return response.json() if response.status_code != 204 else None
            call("POST", "/me/bootstrap")
            account = call("POST", "/accounts", json={"name": "BCA", "type": "bank"})
            food = next(category for category in call("GET", "/categories") if category["name"] == "Food")
            raw = (ROOT / "tests/fixtures/bca-review-fictional.eml").read_bytes()
            staged = call("POST", f"/imports/bca?account_id={account['id']}", data=raw)
            item = staged["item"]
            assert staged["duplicate"] is False
            assert call("GET", "/transactions") == []
            assert call("GET", "/imports")[0]["status"] == "pending"
            payload = {"account_id": account["id"], "category_id": food["id"], "save_rule": True}
            approved = call("POST", f"/imports/{item['id']}/approve", json=payload)
            assert approved["status"] == "imported"
            assert call("POST", f"/imports/{item['id']}/approve", json=payload)["transaction_id"] == approved["transaction_id"]
            assert len(call("GET", "/transactions")) == 1
            assert call("GET", "/imports/rules")[0]["category_id"] == food["id"]
            assert call("POST", f"/imports/bca?account_id={account['id']}", data=raw)["duplicate"] is True
            other = raw.replace(b"review-001", b"review-002").replace(b"REVIEW-001", b"REVIEW-002").replace(b"12:00:00", b"13:00:00")
            suggested = call("POST", f"/imports/bca?account_id={account['id']}", data=other)["item"]
            assert suggested["suggested_category_id"] == food["id"]
            assert suggested["suggestion_source"] == "rule"
            assert call("POST", f"/imports/{suggested['id']}/dismiss")["status"] == "dismissed"
            print("PASS: real Worker parsing, D1 batch approval, rule suggestions, retries and skip", flush=True)
        finally:
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, check=False)


if __name__ == "__main__":
    main()
