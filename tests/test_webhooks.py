import pytest

from app.webhooks import sign_payload, validate_webhook_url


def test_signature_is_deterministic():
    assert sign_payload(b"{}", "1700000000", "secret") == sign_payload(
        b"{}", "1700000000", "secret"
    )


def test_http_webhook_rejected():
    with pytest.raises(ValueError, match="HTTPS"):
        validate_webhook_url("http://example.com/hook", False)
