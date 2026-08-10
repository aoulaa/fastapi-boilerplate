import httpx
import pytest

from app.eskiz.client import EskizClient
from app.eskiz.exceptions import EskizError, EskizUnreachable


async def test_stub_mode_when_unconfigured() -> None:
    """Blank credentials must never raise — local dev and CI depend on it."""
    client = EskizClient()
    client._email = ""
    client._password = ""
    assert (await client.send("998901234567", "hi"))["status"] == "stubbed"
    assert (await client.send_batch([{"mobile_phone": "998901234567", "message": "hi"}]))["status"] == "stubbed"


def _configured() -> EskizClient:
    client = EskizClient()
    client._email = "test@example.com"
    client._password = "secret"
    client._process_token = "cached-token"
    client._redis = None
    return client


async def test_reauth_once_on_401(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _configured()
    calls: list[str] = []

    async def fake_post(self, url, **kwargs):  # noqa: ANN001, ANN202
        calls.append(url)
        if url == "/api/auth/login":
            return httpx.Response(200, json={"data": {"token": "fresh-token"}})
        # First send is rejected (stale token), the retry after re-login passes.
        if calls.count("/api/message/sms/send") == 1:
            return httpx.Response(401, json={"message": "Unauthorized"})
        return httpx.Response(200, json={"status": "waiting"})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    assert await client.send("998901234567", "hi") == {"status": "waiting"}
    assert calls == ["/api/message/sms/send", "/api/auth/login", "/api/message/sms/send"]


async def test_persistent_401_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _configured()

    async def fake_post(self, url, **kwargs):  # noqa: ANN001, ANN202
        if url == "/api/auth/login":
            return httpx.Response(200, json={"data": {"token": "fresh-token"}})
        return httpx.Response(401, json={"message": "Unauthorized"})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    with pytest.raises(EskizError):
        await client.send("998901234567", "hi")


async def test_transport_error_is_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _configured()

    async def fake_post(self, url, **kwargs):  # noqa: ANN001, ANN202
        raise httpx.ConnectTimeout("timed out")

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    with pytest.raises(EskizUnreachable):
        await client.send("998901234567", "hi")
