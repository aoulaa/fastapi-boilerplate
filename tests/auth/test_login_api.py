from httpx import AsyncClient

from app.auth.constants import OTP_COOLDOWN_PREFIX, OTP_PREFIX
from app.redis import get_redis
from app.user.models import User
from tests.conftest import TEST_PASSWORD

NEW_PHONE = "+998901112233"


async def test_otp_flow_registers_a_new_account(client: AsyncClient) -> None:
    """First successful verification creates the user — there is no signup endpoint."""
    redis = await get_redis()
    await redis.delete(f"{OTP_PREFIX}{NEW_PHONE}", f"{OTP_COOLDOWN_PREFIX}{NEW_PHONE}")

    sent = await client.post("/v1/auth/send-otp", json={"phone_number": NEW_PHONE})
    assert sent.status_code == 204

    # Eskiz is unconfigured in tests, so the send is stubbed and the code is
    # readable straight out of Redis.
    code = await redis.get(f"{OTP_PREFIX}{NEW_PHONE}")
    assert code

    verified = await client.post("/v1/auth/verify-otp", json={"phone_number": NEW_PHONE, "code": code})
    assert verified.status_code == 200, verified.text

    me = await client.get("/v1/users/me", headers={"Authorization": f"Bearer {verified.json()['access_token']}"})
    assert me.status_code == 200
    assert me.json()["phone_number"] == NEW_PHONE
    assert me.json()["role"] == "user"

    await redis.delete(f"{OTP_COOLDOWN_PREFIX}{NEW_PHONE}")


async def test_login_and_use_token(client: AsyncClient, user: User) -> None:
    resp = await client.post("/v1/auth/login", json={"phone_number": user.phone_number, "password": TEST_PASSWORD})
    assert resp.status_code == 200, resp.text
    tokens = resp.json()
    assert tokens["token_type"] == "bearer"

    me = await client.get("/v1/users/me", headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert me.status_code == 200
    assert me.json()["phone_number"] == user.phone_number


async def test_refresh_rotates(client: AsyncClient, user: User) -> None:
    login = await client.post("/v1/auth/login", json={"phone_number": user.phone_number, "password": TEST_PASSWORD})
    refresh_token = login.json()["refresh_token"]

    first = await client.post("/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert first.status_code == 200
    assert first.json()["refresh_token"] != refresh_token

    # The consumed token is dead — replaying it must fail.
    replay = await client.post("/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert replay.status_code == 401


async def test_wrong_password_is_indistinguishable_from_unknown_user(client: AsyncClient, user: User) -> None:
    wrong = await client.post("/v1/auth/login", json={"phone_number": user.phone_number, "password": "wrongpass1"})
    unknown = await client.post("/v1/auth/login", json={"phone_number": "+998900000001", "password": "wrongpass1"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["detail"] == unknown.json()["detail"] == "INVALID_CREDENTIALS"


async def test_logout_kills_the_access_token_immediately(client: AsyncClient, user: User) -> None:
    login = await client.post("/v1/auth/login", json={"phone_number": user.phone_number, "password": TEST_PASSWORD})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    assert (await client.post("/v1/auth/logout", headers=headers)).status_code == 204
    # Without the Redis blocklist this would keep working for JWT_EXP minutes.
    assert (await client.get("/v1/users/me", headers=headers)).status_code == 401
