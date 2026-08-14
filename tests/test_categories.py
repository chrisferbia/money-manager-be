"""Tests for specs/0002-expense-categories.md."""

import requests
import pytest


pytestmark = pytest.mark.integration


def test_ac1_create_category_returns_201_with_id(dev_server):
    port = dev_server
    response = requests.post(
        f"http://localhost:{port}/categories",
        json={"name": "AC1 Groceries"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "AC1 Groceries"
    assert isinstance(body["id"], int)
    assert "created_at" in body


def test_ac2_duplicate_name_is_rejected(dev_server):
    port = dev_server
    first = requests.post(
        f"http://localhost:{port}/categories",
        json={"name": "AC2 Duplicate"},
    )
    assert first.status_code == 201

    second = requests.post(
        f"http://localhost:{port}/categories",
        json={"name": "AC2 Duplicate"},
    )
    assert 400 <= second.status_code < 500

    listing = requests.get(f"http://localhost:{port}/categories")
    matches = [category for category in listing.json() if category["name"] == "AC2 Duplicate"]
    assert len(matches) == 1


def test_ac3_list_categories_returns_created_categories(dev_server):
    port = dev_server
    created = requests.post(
        f"http://localhost:{port}/categories",
        json={"name": "AC3 Transport"},
    ).json()

    listing = requests.get(f"http://localhost:{port}/categories")
    assert listing.status_code == 200
    ids = [category["id"] for category in listing.json()]
    assert created["id"] in ids


def test_ac4_get_category_by_id(dev_server):
    port = dev_server
    created = requests.post(
        f"http://localhost:{port}/categories",
        json={"name": "AC4 Dining"},
    ).json()

    found = requests.get(f"http://localhost:{port}/categories/{created['id']}")
    assert found.status_code == 200
    assert found.json()["name"] == "AC4 Dining"


def test_ac4_get_unknown_category_returns_404(dev_server):
    port = dev_server
    response = requests.get(f"http://localhost:{port}/categories/999999")
    assert response.status_code == 404


def test_ac5_patch_updates_persist(dev_server):
    port = dev_server
    created = requests.post(
        f"http://localhost:{port}/categories",
        json={"name": "AC5 Original"},
    ).json()

    updated = requests.patch(
        f"http://localhost:{port}/categories/{created['id']}",
        json={"name": "AC5 Renamed"},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "AC5 Renamed"

    refetched = requests.get(f"http://localhost:{port}/categories/{created['id']}")
    assert refetched.json()["name"] == "AC5 Renamed"


def test_ac5_patch_rejects_blank_and_duplicate_name(dev_server):
    port = dev_server
    created = requests.post(
        f"http://localhost:{port}/categories",
        json={"name": "AC5 BlankGuard"},
    ).json()
    other = requests.post(
        f"http://localhost:{port}/categories",
        json={"name": "AC5 Other"},
    ).json()

    blank_name = requests.patch(
        f"http://localhost:{port}/categories/{created['id']}",
        json={"name": ""},
    )
    assert 400 <= blank_name.status_code < 500

    duplicate = requests.patch(
        f"http://localhost:{port}/categories/{other['id']}",
        json={"name": "AC5 BlankGuard"},
    )
    assert 400 <= duplicate.status_code < 500

    refetched = requests.get(f"http://localhost:{port}/categories/{created['id']}")
    assert refetched.json()["name"] == "AC5 BlankGuard"


def test_ac6_delete_category_then_get_returns_404(dev_server):
    port = dev_server
    created = requests.post(
        f"http://localhost:{port}/categories",
        json={"name": "AC6 ToDelete"},
    ).json()

    deleted = requests.delete(f"http://localhost:{port}/categories/{created['id']}")
    assert deleted.status_code == 204

    refetched = requests.get(f"http://localhost:{port}/categories/{created['id']}")
    assert refetched.status_code == 404
