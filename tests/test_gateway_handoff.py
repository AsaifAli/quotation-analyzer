import json

import pytest
import gateway_handoff

from gateway_handoff import (
    GatewayHandoffError,
    exchange_endpoint,
    exchange_handoff_code,
)


class FakeResponse:
    def __init__(self, payload):
        self.body = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, limit):
        return self.body[:limit]


class FakeOpener:
    def __init__(self, payload, expected_url):
        self.payload = payload
        self.expected_url = expected_url
        self.timeout = None

    def open(self, request, timeout):
        self.timeout = timeout

        assert request.full_url == self.expected_url
        assert request.get_method() == "POST"
        assert request.get_header("Cache-control") == "no-store"

        body = json.loads(request.data.decode("utf-8"))

        assert body == {
            "code": "a" * 43,
            "project": "quotesense",
        }

        return FakeResponse(self.payload)


def test_exchange_endpoint_accepts_root():
    assert exchange_endpoint(
        "https://gateway.example.com"
    ) == (
        "https://gateway.example.com/v1/demo/session/exchange"
    )


def test_exchange_endpoint_accepts_v1():
    assert exchange_endpoint(
        "https://gateway.example.com/v1"
    ) == (
        "https://gateway.example.com/v1/demo/session/exchange"
    )


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "https://user:password@example.com",
        "https://gateway.example.com:invalid",
    ],
)
def test_exchange_rejects_invalid_urls(url):
    with pytest.raises(GatewayHandoffError):
        exchange_endpoint(url)


def test_exchange_returns_valid_session(monkeypatch):
    fake = FakeOpener(
        {
            "access_token": "signed-session-token",
            "expires_in": 900,
            "target_project": "quotesense",
            "provider": "openai",
            "model": "gpt-4o-mini",
        },
        "https://gateway.example.com/v1/demo/session/exchange",
    )

    monkeypatch.setattr(
        gateway_handoff,
        "build_opener",
        lambda *args: fake,
    )

    result = exchange_handoff_code(
        "a" * 43,
        gateway_url="https://gateway.example.com/v1",
    )

    assert result["access_token"] == "signed-session-token"
    assert result["expires_in"] == 900
    assert result["target_project"] == "quotesense"
    assert fake.timeout == 8


def test_exchange_rejects_wrong_project(monkeypatch):
    fake = FakeOpener(
        {
            "access_token": "token",
            "expires_in": 900,
            "target_project": "evidenceflow",
        },
        "https://gateway.example.com/v1/demo/session/exchange",
    )

    monkeypatch.setattr(
        gateway_handoff,
        "build_opener",
        lambda *args: fake,
    )

    with pytest.raises(
        GatewayHandoffError,
        match="unexpected project",
    ):
        exchange_handoff_code(
            "a" * 43,
            gateway_url="https://gateway.example.com",
        )


def test_exchange_rejects_missing_expiry(monkeypatch):
    fake = FakeOpener(
        {
            "access_token": "token",
            "target_project": "quotesense",
        },
        "https://gateway.example.com/v1/demo/session/exchange",
    )

    monkeypatch.setattr(
        gateway_handoff,
        "build_opener",
        lambda *args: fake,
    )

    with pytest.raises(
        GatewayHandoffError,
        match="expiry",
    ):
        exchange_handoff_code(
            "a" * 43,
            gateway_url="https://gateway.example.com",
        )


def test_exchange_rejects_invalid_code():
    with pytest.raises(
        GatewayHandoffError,
        match="invalid or incomplete",
    ):
        exchange_handoff_code(
            "invalid",
            gateway_url="https://gateway.example.com",
        )


def test_exchange_only_allows_quotesense():
    with pytest.raises(
        GatewayHandoffError,
        match="target project",
    ):
        exchange_handoff_code(
            "a" * 43,
            project="evidenceflow",
            gateway_url="https://gateway.example.com",
        )


def test_exchange_requires_gateway_url(monkeypatch):
    monkeypatch.delenv(
        "PORTFOLIO_SESSION_GATEWAY_URL",
        raising=False,
    )

    monkeypatch.setattr(
        gateway_handoff,
        "configured_gateway_url",
        lambda: "",
    )

    with pytest.raises(
        GatewayHandoffError,
        match="not configured",
    ):
        exchange_handoff_code("a" * 43)
