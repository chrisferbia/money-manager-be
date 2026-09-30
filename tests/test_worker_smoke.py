import uuid

import pytest
import requests


pytestmark = pytest.mark.worker


def test_real_worker_requires_sign_in(worker_server):
    port, _ = worker_server
    response = requests.get(f"http://localhost:{port}/accounts")
    assert response.status_code == 401


def test_real_worker_provisions_and_isolates_workspaces(worker_server):
    port, token = worker_server
    alice_headers = {"Authorization": f"Bearer {token('worker-alice')}"}
    bob_headers = {"Authorization": f"Bearer {token('worker-bob')}"}
    for headers in (alice_headers, bob_headers):
        assert requests.post(f"http://localhost:{port}/me/bootstrap", headers=headers).status_code == 200

    name = f"Worker Smoke {uuid.uuid4()}"

    created = requests.post(
        f"http://localhost:{port}/accounts",
        json={"name": name, "type": "cash"},
        headers=alice_headers,
    )
    assert created.status_code == 201

    account_id = created.json()["id"]
    fetched = requests.get(f"http://localhost:{port}/accounts/{account_id}", headers=alice_headers)

    assert fetched.status_code == 200
    assert fetched.json()["name"] == name
    assert requests.get(f"http://localhost:{port}/accounts/{account_id}", headers=bob_headers).status_code == 404
    assert all(account["name"] != name for account in requests.get(
        f"http://localhost:{port}/accounts", headers=bob_headers
    ).json())
