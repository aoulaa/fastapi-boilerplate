"""Eskiz.uz SMS gateway client.

Reference: https://documenter.getpostman.com/view/663428/RzfmES4z

Auth is a bearer token with a 30-day life, so it's cached in Redis (25-day TTL)
and shared across every web and worker process — a fresh login per send would
rate-limit fast. On a 401 the client re-authenticates exactly once and retries;
a second 401 is a real error, not a stale token.
"""

from __future__ import annotations

import logging
from typing import Any, cast

import httpx
import redis.asyncio as redis
import sentry_sdk

from app.config import settings
from app.eskiz.config import eskiz_settings
from app.eskiz.exceptions import EskizError, EskizUnreachable

logger = logging.getLogger(__name__)

_TOKEN_KEY = "sms:eskiz:token"
_TOKEN_TTL_SECONDS = 25 * 24 * 3600  # 25 days — refresh before Eskiz's 30-day expiry

# Cap stored/forwarded reason length. Eskiz error bodies are short, but a stray
# HTML error page shouldn't bloat a DB column or a Sentry event.
_MAX_ERROR_LEN = 500


def record_sms_failure(exc: Exception, *, context: dict[str, Any] | None = None) -> str:
    """Log an SMS failure, forward it to Sentry, and return a trimmed reason string.

    Centralised so every send path (OTP, manual, scheduled) reports failures the
    same way — visible in Sentry *and* persistable on the originating row.
    """
    reason = str(exc).strip() or exc.__class__.__name__
    reason = reason[:_MAX_ERROR_LEN]

    # WARNING (not ERROR) so the logging integration doesn't emit a *second*
    # Sentry event — capture_exception below is the single source.
    logger.warning("SMS send failed: %s", reason)

    with sentry_sdk.new_scope() as scope:
        scope.set_tag("sms.provider", "eskiz")
        scope.set_tag("sms.error_type", exc.__class__.__name__)
        for key, value in (context or {}).items():
            if isinstance(value, dict):
                scope.set_context(key, value)
            else:
                scope.set_tag(key, str(value))
        sentry_sdk.capture_exception(exc)

    return reason


class EskizClient:
    """Async Eskiz.uz client. Safe to share process-wide — connections are pooled per call."""

    def __init__(self) -> None:
        self._email = eskiz_settings.ESKIZ_EMAIL
        self._password = eskiz_settings.ESKIZ_PASSWORD.get_secret_value()
        self._from = eskiz_settings.ESKIZ_FROM
        self._base = eskiz_settings.ESKIZ_BASE_URL.rstrip("/")
        self._redis: redis.Redis | None = None
        self._process_token: str | None = None  # fallback when Redis is unavailable

    @property
    def is_configured(self) -> bool:
        return bool(self._email and self._password)

    # ---- Redis token cache ----

    async def _get_redis(self) -> redis.Redis | None:
        if self._redis is not None:
            return self._redis
        try:
            self._redis = redis.from_url(settings.REDIS_URL, decode_responses=True)
            await self._redis.ping()
        except Exception as exc:
            logger.info("Eskiz: Redis unavailable (%s); using process-local token cache", exc)
            self._redis = None
        return self._redis

    async def _cached_token(self) -> str | None:
        r = await self._get_redis()
        if r is not None:
            value = await r.get(_TOKEN_KEY)
            if value:
                return str(value)
        return self._process_token

    async def _store_token(self, token: str) -> None:
        self._process_token = token
        r = await self._get_redis()
        if r is not None:
            await r.set(_TOKEN_KEY, token, ex=_TOKEN_TTL_SECONDS)

    async def _clear_token(self) -> None:
        self._process_token = None
        r = await self._get_redis()
        if r is not None:
            await r.delete(_TOKEN_KEY)

    # ---- Auth ----

    async def _login(self) -> str:
        if not self.is_configured:
            raise EskizUnreachable("ESKIZ_EMAIL / ESKIZ_PASSWORD not configured")

        try:
            async with httpx.AsyncClient(base_url=self._base, timeout=10.0) as client:
                resp = await client.post(
                    "/api/auth/login",
                    data={"email": self._email, "password": self._password},
                )
        except httpx.HTTPError as exc:
            raise EskizUnreachable(f"Eskiz login transport error: {exc}") from exc

        if resp.status_code != 200:
            raise EskizUnreachable(f"Eskiz login failed: {resp.status_code} {resp.text}")

        token = resp.json().get("data", {}).get("token")
        if not token:
            raise EskizUnreachable(f"Eskiz login returned no token: {resp.text}")
        await self._store_token(token)
        logger.info("Eskiz: obtained fresh token")
        return str(token)

    async def _token(self) -> str:
        cached = await self._cached_token()
        if cached:
            return cached
        return await self._login()

    async def _post_with_reauth(
        self,
        path: str,
        *,
        timeout: float,
        data: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> httpx.Response:
        """POST with the cached token; on 401 re-login once and retry."""

        async def _do(token: str) -> httpx.Response:
            try:
                async with httpx.AsyncClient(base_url=self._base, timeout=timeout) as client:
                    return await client.post(
                        path,
                        data=data,
                        json=json,
                        headers={"Authorization": f"Bearer {token}"},
                    )
            except httpx.HTTPError as exc:
                raise EskizUnreachable(f"Eskiz transport error on {path}: {exc}") from exc

        resp = await _do(await self._token())
        if resp.status_code == 401:
            logger.info("Eskiz: token rejected, re-logging in once")
            await self._clear_token()
            resp = await _do(await self._login())
        return resp

    @staticmethod
    def _parse(resp: httpx.Response, what: str) -> dict[str, Any]:
        if resp.status_code >= 400:
            raise EskizError(f"Eskiz {what} failed: {resp.status_code} {resp.text}")
        try:
            return cast(dict[str, Any], resp.json())
        except Exception as exc:
            raise EskizError(f"Eskiz returned non-JSON body: {resp.text}") from exc

    # ---- Public API ----

    async def send(self, phone: str, message: str) -> dict[str, Any]:
        """Send one SMS. `phone` is digits-only international form, e.g. `998901234567`.

        Raises:
            EskizUnreachable: transport failure; the request never reached Eskiz.
            EskizError: Eskiz returned an error status; treat as billable.
        """
        if not self.is_configured:
            # Never log the phone or body: Sentry keeps INFO as breadcrumbs and
            # that would leak PII. Length only.
            logger.info("Eskiz not configured — stubbing send (%d chars)", len(message))
            return {"status": "stubbed", "phone": phone}

        resp = await self._post_with_reauth(
            "/api/message/sms/send",
            timeout=15.0,
            data={"mobile_phone": phone, "message": message, "from": self._from},
        )
        return self._parse(resp, "send")

    async def send_batch(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        """Send many SMS in one request.

        Each item: ``{"mobile_phone": "998...", "message": "...", "user_sms_id": "<unique>"}``.
        `user_sms_id` is optional but strongly recommended — it's how a delivery
        callback is matched back to the originating row.
        """
        if not self.is_configured:
            logger.info("Eskiz not configured — stubbing batch of %d", len(messages))
            return {"status": "stubbed", "count": len(messages)}

        dispatches = [
            {
                "mobile_phone": m["mobile_phone"],
                "message": m["message"],
                "from": self._from,
                **({"user_sms_id": m["user_sms_id"]} if "user_sms_id" in m else {}),
            }
            for m in messages
        ]
        resp = await self._post_with_reauth(
            "/api/message/sms/send-batch",
            timeout=30.0,
            json={"messages": dispatches},
        )
        return self._parse(resp, "batch send")

    async def balance(self) -> dict[str, Any]:
        """Remaining account balance. Useful for a monitoring cron."""
        if not self.is_configured:
            return {"status": "stubbed"}
        resp = await self._post_with_reauth("/api/user/get-limit", timeout=10.0)
        return self._parse(resp, "balance")


eskiz_client = EskizClient()
