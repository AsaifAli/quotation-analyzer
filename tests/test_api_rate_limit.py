import pytest
from fastapi.testclient import TestClient

import config
from api_rate_limit import (AdaptiveRateLimiter, RateLimitBackendUnavailable, SlidingWindowRateLimiter)
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



def test_production_quota_uses_shared_upstash_and_hashes_counter_key(monkeypatch):
    class FakeRedis:
        def __init__(self):
            self.counts = {}
            self.calls = []

        def eval(self, script, *, keys, args):
            self.calls.append((script, keys, args))
            key = keys[0]
            self.counts[key] = self.counts.get(key, 0) + 1
            return [self.counts[key], args[0]]

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("UPSTASH_REDIS_REST_URL", "https://redis.example")
    monkeypatch.setenv("UPSTASH_REDIS_REST_TOKEN", "test-token")
    limiter = AdaptiveRateLimiter()
    client = FakeRedis()
    limiter._client = client

    assert limiter.check("ip:203.0.113.10", limit=1) == (True, 60)
    assert limiter.check("ip:203.0.113.10", limit=1) == (False, 60)
    script, keys, args = client.calls[0]
    assert "INCR" in script and "EXPIRE" in script
    assert len(keys) == 1 and keys[0].startswith("quotesense:ratelimit:v1:")
    assert "203.0.113.10" not in keys[0]
    assert args == [60]


def test_production_quota_fails_closed_without_upstash_credentials(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("UPSTASH_REDIS_REST_URL", raising=False)
    monkeypatch.delenv("UPSTASH_REDIS_REST_TOKEN", raising=False)

    with pytest.raises(RateLimitBackendUnavailable):
        AdaptiveRateLimiter().check("ip:missing", limit=1)



def test_gateway_sessions_get_independent_principal_rate_limit_buckets(monkeypatch):
    import api_security

    monkeypatch.setattr(config, "API_AUTH_TOKEN", "")
    monkeypatch.setattr(config, "API_RATE_LIMIT_PER_MINUTE", 1)
    monkeypatch.setattr(config, "API_IP_RATE_LIMIT_PER_MINUTE", 20)
    monkeypatch.setattr(
        api_security,
        "verify_gateway_session",
        lambda token: {"active": True, "project": "quotesense", "owner_scope": "a" * 64},
    )

    from api_rate_limit import rate_limiter
    rate_limiter.clear()
    client = TestClient(app)

    first = client.post(
        "/api/v1/analyses",
        headers={"X-LLM-Gateway-Token": "gateway-session-one"},
    )
    second = client.post(
        "/api/v1/analyses",
        headers={"X-LLM-Gateway-Token": "gateway-session-two"},
    )
    third = client.post(
        "/api/v1/analyses",
        headers={"X-LLM-Gateway-Token": "gateway-session-one"},
    )

    # No files are supplied, so each authenticated request reaches FastAPI's
    # 422 validation; only the third request exceeds the first session quota.
    assert first.status_code == 422
    assert second.status_code == 422
    assert third.status_code == 429
