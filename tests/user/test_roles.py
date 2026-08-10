from httpx import AsyncClient

from app.user.models import User
from tests.conftest import auth_headers


async def test_plain_user_cannot_list_users(client: AsyncClient, user: User) -> None:
    resp = await client.get("/v1/users", headers=auth_headers(user))
    assert resp.status_code == 403
    assert resp.json()["detail"] == "INSUFFICIENT_ROLE"


async def test_admin_can_list_users(client: AsyncClient, admin: User) -> None:
    resp = await client.get("/v1/users", headers=auth_headers(admin))
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1


async def test_self_update_cannot_escalate_role(client: AsyncClient, user: User) -> None:
    """`role` isn't in UserUpdate, so it's ignored rather than applied."""
    resp = await client.patch(
        "/v1/users/me", json={"full_name": "New Name", "role": "admin"}, headers=auth_headers(user)
    )
    assert resp.status_code == 200
    assert resp.json()["full_name"] == "New Name"
    assert resp.json()["role"] == "user"


async def test_deactivated_user_is_locked_out(client: AsyncClient, admin: User, user: User) -> None:
    patched = await client.patch(f"/v1/users/{user.id}", json={"is_active": False}, headers=auth_headers(admin))
    assert patched.status_code == 200

    resp = await client.get("/v1/users/me", headers=auth_headers(user))
    assert resp.status_code == 403
    assert resp.json()["detail"] == "ACCOUNT_DEACTIVATED"
