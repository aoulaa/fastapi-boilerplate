import pytest

from app.eskiz.errors import SmsErrorCode, classify_sms_error, is_retryable
from app.eskiz.exceptions import EskizError, EskizUnreachable


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Eskiz send failed: 400 SMSC not found", SmsErrorCode.INVALID_NUMBER),
        ("неверный номер получателя", SmsErrorCode.INVALID_NUMBER),
        ("Message is not moderated yet", SmsErrorCode.NOT_MODERATED),
        ("сообщение не прошло модерацию", SmsErrorCode.NOT_MODERATED),
        ("insufficient funds on your balance", SmsErrorCode.INSUFFICIENT_BALANCE),
        ("недостаточно средств", SmsErrorCode.INSUFFICIENT_BALANCE),
        ("something we have never seen", SmsErrorCode.PROVIDER_ERROR),
    ],
)
def test_provider_text_is_classified(message: str, expected: SmsErrorCode) -> None:
    assert classify_sms_error(EskizError(message)) is expected


def test_transport_failure_is_retryable() -> None:
    code = classify_sms_error(EskizUnreachable("timeout"))
    assert code is SmsErrorCode.PROVIDER_UNREACHABLE
    assert is_retryable(code)


def test_unexpected_exception_is_internal() -> None:
    assert classify_sms_error(ValueError("boom")) is SmsErrorCode.INTERNAL


def test_bad_number_is_not_retryable() -> None:
    """Retrying a malformed number burns credits forever — it must be terminal."""
    assert not is_retryable(SmsErrorCode.INVALID_NUMBER)
