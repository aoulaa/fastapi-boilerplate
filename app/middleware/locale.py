from starlette.types import ASGIApp, Receive, Scope, Send

from app.constants import Language
from app.i18n import _current_language

_DEFAULT = Language.EN


def _parse_language(accept_language: str) -> Language:
    """First supported language in the header, else the default.

    Deliberately simple: quality values are ignored, only the 2-letter prefix
    is compared. Clients send an explicit single language in practice.
    """
    for part in accept_language.split(","):
        code = part.split(";")[0].strip().lower()[:2]
        try:
            return Language(code)
        except ValueError:
            continue
    return _DEFAULT


class LocaleMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        accept_lang = headers.get(b"accept-language", b"").decode("latin-1")
        token = _current_language.set(_parse_language(accept_lang))
        try:
            await self.app(scope, receive, send)
        finally:
            # Reset so the ContextVar never leaks into the next request served
            # on this task.
            _current_language.reset(token)
