from types import SimpleNamespace

import pytest

from modules.ai_agent import QuotationIntelligenceAgent


def make_agent(result=None, error=None):
    agent = object.__new__(QuotationIntelligenceAgent)

    def fake_process_documents(*args, **kwargs):
        if error:
            raise error
        return result

    agent._process_documents = fake_process_documents
    return agent


def test_completed_analysis_reports_only_bounded_metrics(monkeypatch):
    events = []
    monkeypatch.setattr("modules.ai_agent.record_event", lambda **event: events.append(event) or True)
    result = {
        "status": "success",
        "model": "test-model",
        "metrics": {"document_count": 2, "quotation_count": 4},
        "risks": [{"category": "terms"}],
        "price_anomalies": [],
        "documents": [{"source": "confidential-supplier.pdf"}],
        "quotations": [{"supplier": "Confidential Supplier"}],
    }

    returned = make_agent(result=result).process_documents(["/tmp/private.pdf"])

    assert returned is result
    assert len(events) == 1
    event = events[0]
    assert event["project"] if "project" in event else True
    assert event["event_type"] == "run.completed"
    assert event["status"] == "success"
    assert event["workflow"] == "quotation_analysis"
    assert event["model"] == "test-model"
    assert event["metrics"] == {
        "document_count": 2,
        "quotation_count": 4,
        "risk_count": 1,
        "price_anomaly_count": 0,
    }
    assert "documents" not in event
    assert "quotations" not in event


def test_failed_analysis_is_reported_and_exception_is_preserved(monkeypatch):
    events = []
    monkeypatch.setattr("modules.ai_agent.record_event", lambda **event: events.append(event) or True)
    error = RuntimeError("analysis failed")

    with pytest.raises(RuntimeError, match="analysis failed"):
        make_agent(error=error).process_documents(["/tmp/private.pdf"])

    assert len(events) == 1
    assert events[0]["event_type"] == "run.failed"
    assert events[0]["status"] == "failed"
