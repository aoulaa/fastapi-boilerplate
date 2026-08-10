"""Request-scoped translations.

The active language is a ContextVar set by `LocaleMiddleware` from the
`Accept-Language` header, so `_("...")` works anywhere in the request without
threading a locale argument through every call. Background jobs call
`set_language()` explicitly before rendering user-facing text.

Workflow: `make babel-extract` → `make babel-update` → translate the `.po`
files → `make babel-compile`.
"""

from contextvars import ContextVar
from pathlib import Path

from babel.support import NullTranslations, Translations

from app.constants import Language

_LOCALES_DIR = Path(__file__).parent.parent / "locales"
_current_language: ContextVar[Language] = ContextVar("language", default=Language.EN)

_translations: dict[Language, Translations | NullTranslations] = {}


def _load() -> None:
    for lang in Language:
        try:
            _translations[lang] = Translations.load(_LOCALES_DIR, [lang.value])
        except Exception:
            # Missing/uncompiled catalogue — fall back to the msgid verbatim
            # rather than breaking startup.
            _translations[lang] = NullTranslations()


_load()


def set_language(lang: Language) -> None:
    _current_language.set(lang)


def get_language() -> Language:
    return _current_language.get()


def _(message: str) -> str:
    t = _translations.get(_current_language.get())
    return t.gettext(message) if t else message
