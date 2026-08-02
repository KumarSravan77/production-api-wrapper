import os

import pytest
from fastapi.testclient import TestClient

os.environ["WRAPPER_API_KEYS"] = "test-key"
os.environ["RATE_LIMIT_REQUESTS"] = "2"

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
