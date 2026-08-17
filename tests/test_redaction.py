from app.redaction import redact_sensitive


def test_redacts_nested_sensitive_values():
    payload = {
        "messages": [{"role": "user", "content": "Email buyer@example.ca"}],
        "card": "4111 1111 1111 1111",
        "safe": "winter jacket",
    }
    redacted, count = redact_sensitive(payload)
    assert redacted["messages"][0]["content"] == "Email [REDACTED]"
    assert redacted["card"] == "[REDACTED]"
    assert redacted["safe"] == "winter jacket"
    assert count == 2
