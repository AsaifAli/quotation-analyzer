import json

from harness_telemetry import record_event


class FakeResponse:
    status = 202

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_telemetry_is_disabled_without_configuration(monkeypatch):
    monkeypatch.delenv("EVALUATION_HARNESS_URL", raising=False)
    monkeypatch.delenv("EVALUATION_HARNESS_INGEST_TOKEN", raising=False)
    assert record_event(event_type="run.completed", status="success", workflow="quotation_analysis") is False


def test_telemetry_sends_only_numeric_metadata(monkeypatch):
    import harness_telemetry

    monkeypatch.setenv("EVALUATION_HARNESS_URL", "https://example.invalid")
    monkeypatch.setenv("EVALUATION_HARNESS_INGEST_TOKEN", "quotesense-test-token")
    sent = {}

    def fake_urlopen(request, timeout):
        sent["payload"] = json.loads(request.data.decode("utf-8"))
        sent["authorization"] = request.get_header("Authorization")
        sent["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(harness_telemetry, "urlopen", fake_urlopen)
    assert record_event(
        event_type="run.completed",
        status="success",
        workflow="quotation_analysis",
        duration_ms=21,
        model="test-model",
        metrics={"quotation_count": 3, "risk_count": 1, "supplier_name": "private supplier"},
    )

    assert sent["payload"]["project"] == "quotesense"
    assert sent["payload"]["metrics"] == {"quotation_count": 3, "risk_count": 1}
    assert sent["authorization"] == "Bearer quotesense-test-token"
    assert sent["timeout"] == 1.25
