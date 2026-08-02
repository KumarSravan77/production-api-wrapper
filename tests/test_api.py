import os

import pytest
from fastapi.testclient import TestClient

os.environ["WRAPPER_API_KEYS"] = "test-key"
os.environ["RATE_LIMIT_REQUESTS"] = "2"
os.environ["ALLOWED_MODEL_ALIASES"] = "fast,balanced,reasoning,private"
os.environ["DEFAULT_MODEL_ALIAS"] = "balanced"

from app.config import get_settings
from app.main import app


@pytest.fixture
def client():
    get_settings.cache_clear()
    with TestClient(app) as test_client:
        yield test_client


def test_health(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.headers["x-request-id"]


def test_auth(client):
    response = client.post("/v1/generate", json={"input": "hello"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_structured_provider_error(client):
    response = client.post(
        "/v1/generate", headers={"X-API-Key": "test-key"}, json={"input": "hello"}
    )
    assert response.status_code == 503
    assert response.json()["error"]["request_id"] == response.headers["x-request-id"]


def test_rate_limit(client):
    headers = {"X-API-Key": "test-key"}
    client.post("/v1/generate", headers=headers, json={"input": "one"})
    client.post("/v1/generate", headers=headers, json={"input": "two"})
    response = client.post("/v1/generate", headers=headers, json={"input": "three"})
    assert response.status_code == 429


class FakeProvider:
    async def create_chat_completion(self, payload, request_id):
        return {"id": "chatcmpl_test", "model": payload["model"], "choices": []}

    async def create_response(self, payload, request_id):
        return {"id": "resp_test", "model": payload["model"], "output": []}

    async def stream(self, endpoint, payload, request_id):
        yield b'data: {"type":"response.output_text.delta","delta":"hello"}\n\n'
        yield b"data: [DONE]\n\n"


def test_chat_completion_uses_default_policy_alias(client):
    client.app.state.provider = FakeProvider()
    response = client.post(
        "/v1/chat/completions",
        headers={"X-API-Key": "test-key"},
        json={"messages": [{"role": "user", "content": "hello"}]},
    )
    assert response.status_code == 200
    assert response.json()["model"] == "balanced"
    assert response.headers["x-model-policy"] == "alias-only"


def test_direct_provider_model_is_rejected(client):
    response = client.post(
        "/v1/responses",
        headers={"X-API-Key": "test-key"},
        json={"model": "openai/some-provider-model", "input": "hello"},
    )
    assert response.status_code == 422
    assert "not allowed" in response.json()["error"]["message"]


def test_output_limit_is_enforced_before_provider_call(client):
    response = client.post(
        "/v1/chat/completions",
        headers={"X-API-Key": "test-key"},
        json={
            "model": "fast",
            "messages": [{"role": "user", "content": "hello"}],
            "max_completion_tokens": 9000,
        },
    )
    assert response.status_code == 422
    assert "capped" in response.json()["error"]["message"]


def test_responses_stream_is_forwarded_as_server_sent_events(client):
    client.app.state.provider = FakeProvider()
    response = client.post(
        "/v1/responses",
        headers={"X-API-Key": "test-key"},
        json={"model": "reasoning", "input": "hello", "stream": True},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "response.output_text.delta" in response.text
    assert "[DONE]" in response.text
