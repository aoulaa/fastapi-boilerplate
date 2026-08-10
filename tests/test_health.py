from httpx import AsyncClient


async def test_health_ok(client: AsyncClient) -> None:
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_request_id_header(client: AsyncClient) -> None:
    """Every response carries a correlation id — a user-reported failure has to
    be traceable to a log line."""
    resp = await client.get("/health")
    assert resp.headers.get("x-request-id")


async def test_protected_endpoint_requires_token(client: AsyncClient) -> None:
    resp = await client.get("/v1/items")
    assert resp.status_code == 401
