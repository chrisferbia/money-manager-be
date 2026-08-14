import uuid

import pytest
import requests


pytestmark = pytest.mark.worker


def test_real_worker_renders_dashboard(worker_server):
    response = requests.get(f"http://localhost:{worker_server}/")

    assert response.status_code == 200
    assert "Money Manager" in response.text


def test_real_worker_persists_account_in_d1(worker_server):
    port = worker_server
    name = f"Worker Smoke {uuid.uuid4()}"

    created = requests.post(
        f"http://localhost:{port}/accounts",
        json={"name": name, "type": "cash"},
    )
    assert created.status_code == 201

    account_id = created.json()["id"]
    fetched = requests.get(f"http://localhost:{port}/accounts/{account_id}")

    assert fetched.status_code == 200
    assert fetched.json()["name"] == name
