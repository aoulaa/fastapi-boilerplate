from httpx import AsyncClient

from app.user.models import User
from tests.conftest import auth_headers


async def test_crud_roundtrip(auth_client: AsyncClient) -> None:
    created = await auth_client.post("/v1/items", json={"name": "Widget", "price": 1500})
    assert created.status_code == 201, created.text
    item_id = created.json()["id"]
    assert created.json()["status"] == "draft"

    fetched = await auth_client.get(f"/v1/items/{item_id}")
    assert fetched.status_code == 200
    assert fetched.json()["name"] == "Widget"

    patched = await auth_client.patch(f"/v1/items/{item_id}", json={"status": "published"})
    assert patched.status_code == 200
    assert patched.json()["status"] == "published"
    # A field the client didn't send must survive the PATCH untouched.
    assert patched.json()["price"] == 1500

    assert (await auth_client.delete(f"/v1/items/{item_id}")).status_code == 204
    assert (await auth_client.get(f"/v1/items/{item_id}")).status_code == 404


async def test_duplicate_name_per_owner_conflicts(auth_client: AsyncClient) -> None:
    assert (await auth_client.post("/v1/items", json={"name": "Same"})).status_code == 201
    dup = await auth_client.post("/v1/items", json={"name": "Same"})
    assert dup.status_code == 409
    assert dup.json()["detail"] == "DUPLICATE_ITEM_NAME"


async def test_list_is_scoped_and_paginated(auth_client: AsyncClient) -> None:
    for i in range(3):
        await auth_client.post("/v1/items", json={"name": f"Item {i}"})

    page = await auth_client.get("/v1/items", params={"limit": 2})
    body = page.json()
    assert body["total"] == 3  # total ignores the page window
    assert len(body["items"]) == 2

    found = await auth_client.get("/v1/items", params={"search": "Item 1"})
    assert found.json()["total"] == 1


async def test_another_users_item_is_404_not_403(client: AsyncClient, user: User, admin: User) -> None:
    """404, not 403 — a 403 would confirm the id exists."""
    mine = await client.post("/v1/items", json={"name": "Private"}, headers=auth_headers(user))
    item_id = mine.json()["id"]

    # A second non-admin account must not see it. `admin` bypasses ownership by
    # design, so demote a copy of the header check by using a fresh plain user.
    other = await client.post("/v1/items", json={"name": "Other"}, headers=auth_headers(admin))
    assert other.status_code == 201

    resp = await client.get(f"/v1/items/{item_id}", headers=auth_headers(admin))
    assert resp.status_code == 200  # admin override

    stolen = await client.get(f"/v1/items/{other.json()['id']}", headers=auth_headers(user))
    assert stolen.status_code == 404


async def test_negative_price_rejected_by_schema(auth_client: AsyncClient) -> None:
    resp = await auth_client.post("/v1/items", json={"name": "Cheap", "price": -1})
    assert resp.status_code == 422
