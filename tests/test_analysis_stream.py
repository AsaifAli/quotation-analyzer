import json

from fastapi.testclient import TestClient

import config
from app import app


client = TestClient(app)


def test_analysis_stream_requires_the_same_authenticated_project_session(monkeypatch):
    monkeypatch.setattr(config, "API_AUTH_TOKEN", "stream-test-secret")

    response = client.post(
        "/api/v1/analyses/stream",
        files=[("files", ("quote.txt", b"synthetic quotation", "text/plain"))],
    )

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_analysis_stream_emits_stage_events_and_the_unchanged_analysis_result(monkeypatch):
    monkeypatch.setattr(config, "API_AUTH_TOKEN", "stream-test-secret")

    class DummyAgent:
        def __init__(self, gateway_token=""):
            assert gateway_token == ""

        def process_documents(self, paths, query, criteria, stage_callback=None):
            assert len(paths) == 1
            assert query == "Compare synthetic quotations"
            assert criteria == ["cost", "terms"]
            stage_callback({
                "sequence": 1,
                "stage": "extract",
                "status": "started",
                "message": "Extracting structured supplier information.",
                "metrics": {"document_index": 1, "document_count": 1},
            })
            stage_callback({
                "sequence": 2,
                "stage": "extract",
                "status": "completed",
                "message": "Structured extraction completed.",
                "metrics": {"document_index": 1, "document_count": 1, "quotation_count": 1},
            })
            return {
                "status": "success",
                "quotations": [{"supplier": "Synthetic Supplier", "total_cost": 100, "currency": "INR"}],
                "scores": [{"supplier": "Synthetic Supplier", "score": 90}],
                "processing_trace": [],
            }

    monkeypatch.setattr("app.QuotationIntelligenceAgent", DummyAgent)
    response = client.post(
        "/api/v1/analyses/stream",
        headers={"Authorization": "Bearer stream-test-secret", "Accept": "text/event-stream"},
        data={
            "query": "Compare synthetic quotations",
            "criteria": "cost,terms",
        },
        files=[("files", ("synthetic.txt", b"synthetic quotation content", "text/plain"))],
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = []
    event_name = "message"
    data_lines = []

    def flush_event():
        if data_lines:
            events.append((event_name, json.loads("\\n".join(data_lines))))
            data_lines.clear()

    for line in response.text.splitlines():
        if not line:
            flush_event()
        elif line.startswith("event: "):
            event_name = line[7:]
        elif line.startswith("data: "):
            data_lines.append(line[6:])
    flush_event()

    assert any(name == "stage" and payload["stage"] == "ingest" for name, payload in events)
    assert any(name == "stage" and payload["stage"] == "extract" for name, payload in events)
    result = next(payload for name, payload in events if name == "result")
    assert result["status"] == "success"
    assert result["scores"][0]["score"] == 90
