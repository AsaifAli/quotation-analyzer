import pytest
from fastapi.testclient import TestClient

import config
from api_rate_limit import SlidingWindowRateLimiter
from app import app


def test_sliding_window_limiter_allows_limit_then_rejects():
    now = [100.0]
    limiter = SlidingWindowRateLimiter(clock=lambda: now[0])

    assert limiter.check("client-a", limit=2, window_seconds=60) == (True, 0)
    assert limiter.check("client-a", limit=2, window_seconds=60) == (True, 0)
    allowed, retry_after = limiter.check(
        "client-a", limit=2, window_seconds=60
    )
    assert allowed is False
    assert retry_after == 60

    now[0] += 60
    assert limiter.check("client-a", limit=2, window_seconds=60) == (True, 0)


def test_analysis_endpoint_limits_authenticated_client(monkeypatch):
    monkeypatch.setattr(config, "API_AUTH_TOKEN", "test-secret")
    monkeypatch.setattr(config, "API_RATE_LIMIT_PER_MINUTE", 1)
    monkeypatch.setattr(config, "API_IP_RATE_LIMIT_PER_MINUTE", 20)
    from api_rate_limit import rate_limiter
    rate_limiter.clear()

    client = TestClient(app)
    headers = {"Authorization": "Bearer test-secret"}

    first = client.post("/api/v1/analyses", headers=headers)
    second = client.post("/api/v1/analyses", headers=headers)

    assert first.status_code == 422
    assert second.status_code == 429
    assert second.headers["retry-after"]


def test_analysis_endpoint_limits_invalid_auth_by_ip(monkeypatch):
    monkeypatch.setattr(config, "API_AUTH_TOKEN", "test-secret")
    monkeypatch.setattr(config, "API_RATE_LIMIT_PER_MINUTE", 10)
    monkeypatch.setattr(config, "API_IP_RATE_LIMIT_PER_MINUTE", 1)
    from api_rate_limit import rate_limiter
    rate_limiter.clear()

    client = TestClient(app)
    first = client.post("/api/v1/analyses")
    second = client.post("/api/v1/analyses")

    assert first.status_code == 401
    assert second.status_code == 429
    assert second.headers["retry-after"]
