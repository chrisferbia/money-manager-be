"""Exercise the real Python Worker parser preview with an explicitly local binding."""
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
                    response = requests.post(base + "/email-tools/bca/preview", timeout=1)
                    if response.status_code == 401:
                        ready = True
                        break
                except requests.RequestException:
                    pass
                time.sleep(0.5)
            if not ready:
                raise RuntimeError("Local Worker failed to start: " + log_path.read_text(encoding="utf-8", errors="replace")[-4000:])
            print("Local Worker ready; verifying parser previews never change the ledger", flush=True)
            def call(method, path, **kwargs):
                response = requests.request(method, base + path, headers=headers, timeout=20, **kwargs)
                assert response.ok, f"{path}: {response.status_code} {response.text}"
                return response.json() if response.status_code != 204 else None
            call("POST", "/me/bootstrap")
            account = call("POST", "/accounts", json={"name": "BCA", "type": "bank"})
            food = next(category for category in call("GET", "/categories") if category["name"] == "Food")
            raw = (ROOT / "tests/fixtures/bca-review-fictional.eml").read_bytes()
            call("POST", "/transactions", json={"type": "expense", "account_id": account["id"], "category_id": food["id"], "amount": 100})
            paths = ["/accounts?include_balance=true", "/categories", "/transactions", "/reports/expenses-by-category"]
            before = {path: call("GET", path) for path in paths}
            for _ in range(3):
                result = call("POST", "/email-tools/bca/preview", data=raw)
                assert result["persisted"] is False
                assert result["format_valid"] is True
                assert result["parsed"]["amount"] == 35000
                assert result["default_category"] == "Other"
            malformed = requests.post(base + "/email-tools/bca/preview", headers=headers, data=b"not an email", timeout=20)
            assert malformed.status_code == 400
            assert {path: call("GET", path) for path in paths} == before
            assert requests.post(base + "/imports/1/approve", headers=headers, json={"account_id": account["id"], "category_id": food["id"]}, timeout=20).status_code == 404
            print("PASS: real Worker parsing, repeat/error safety, unchanged balances/ledger/reports and disabled approval", flush=True)
        finally:
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, check=False)


if __name__ == "__main__":
    main()
