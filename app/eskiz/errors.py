"""Machine-readable SMS delivery error codes + classifier.

Eskiz returns free-text provider messages (often English/Russian, e.g.
"SMSC not found"). Surfacing those verbatim leaks technical jargon into the UI
and never gets translated. Instead every failure is classified into a stable
`SmsErrorCode` — the same contract every other module follows: the backend
emits an UPPERCASE code, the client maps it to a localized string.

The raw provider text is still logged and mirrored to Sentry for support; only
the *code* drives the UI.
"""

from __future__ import annotations

from enum import StrEnum

from app.eskiz.exceptions import EskizError, EskizUnreachable


class SmsErrorCode(StrEnum):
    # Recipient number is invalid or unroutable — no operator/SMSC owns the
    # prefix, wrong format, etc. Eskiz's "SMSC not found" lands here.
    INVALID_NUMBER = "INVALID_NUMBER"
    # Message body hasn't passed Eskiz moderation yet (custom text on a nickname
    # that only allows approved templates).
    NOT_MODERATED = "NOT_MODERATED"
    # Eskiz account is out of balance.
    INSUFFICIENT_BALANCE = "INSUFFICIENT_BALANCE"
    # Never reached Eskiz (DNS/timeout/network). Retryable — park the row and
    # retry rather than marking it permanently failed.
    PROVIDER_UNREACHABLE = "PROVIDER_UNREACHABLE"
    # Eskiz rejected the send for a reason not specifically mapped below.
    PROVIDER_ERROR = "PROVIDER_ERROR"
    # Our-side failure (unexpected exception, worker died mid-send).
    INTERNAL = "INTERNAL"


# Substring → code. Matched case-insensitively against the provider text, in
# order (first hit wins). Covers Eskiz's English and Russian wordings. Extend
# this table as new provider messages show up in Sentry — the client needs no
# change, since it maps the *code*.
_SUBSTRING_RULES: tuple[tuple[tuple[str, ...], SmsErrorCode], ...] = (
    (
        ("smsc not found", "not found", "invalid number", "invalid phone", "неверный номер", "не найден"),
        SmsErrorCode.INVALID_NUMBER,
    ),
    # "moderat" (not "moderation") so it matches "moderated" / "moderation" both.
    (("модерац", "moderat", "не прош"), SmsErrorCode.NOT_MODERATED),
    (("insufficient", "balance", "баланс", "недостаточно"), SmsErrorCode.INSUFFICIENT_BALANCE),
)


def _classify_text(text: str) -> SmsErrorCode:
    """Map an Eskiz provider message to a code. Unknown wording → PROVIDER_ERROR."""
    lowered = text.lower()
    for needles, code in _SUBSTRING_RULES:
        if any(needle in lowered for needle in needles):
            return code
    return SmsErrorCode.PROVIDER_ERROR


def classify_sms_error(exc: Exception) -> SmsErrorCode:
    """Classify an SMS send failure into a stable `SmsErrorCode`.

    - `EskizUnreachable` (transport) → PROVIDER_UNREACHABLE (retryable).
    - `EskizError` (endpoint rejected) → classified from the message text.
    - Anything else (our-side / unexpected) → INTERNAL.
    """
    if isinstance(exc, EskizUnreachable):
        return SmsErrorCode.PROVIDER_UNREACHABLE
    if isinstance(exc, EskizError):
        return _classify_text(str(exc))
    return SmsErrorCode.INTERNAL


def is_retryable(code: SmsErrorCode) -> bool:
    """Whether a redelivery attempt could plausibly succeed.

    A bad number or an unmoderated template will fail identically forever;
    an unreachable provider or an empty balance may not.
    """
    return code in (
        SmsErrorCode.PROVIDER_UNREACHABLE,
        SmsErrorCode.INSUFFICIENT_BALANCE,
        SmsErrorCode.INTERNAL,
    )
