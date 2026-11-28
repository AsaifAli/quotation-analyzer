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
    assert len(events) == 2
    event = events[0]
    evaluation_event = events[1]
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
    assert evaluation_event["event_type"] == "evaluation.completed"
    assert evaluation_event["status"] == "success"
    assert evaluation_event["workflow"] == "quotation_analysis"
    assert evaluation_event["metrics"]["procurement.document_count"] == 2
    assert evaluation_event["metrics"]["procurement.quote_count"] == 4
    assert evaluation_event["metrics"]["runtime.risk_finding_count"] == 1
    assert evaluation_event["metrics"]["runtime.price_anomaly_count"] == 0
    assert "Confidential Supplier" not in str(evaluation_event)
    assert "confidential-supplier.pdf" not in str(evaluation_event)


def test_failed_analysis_is_reported_and_exception_is_preserved(monkeypatch):
    events = []
    monkeypatch.setattr("modules.ai_agent.record_event", lambda **event: events.append(event) or True)
    error = RuntimeError("analysis failed")

    with pytest.raises(RuntimeError, match="analysis failed"):
        make_agent(error=error).process_documents(["/tmp/private.pdf"])

    assert len(events) == 1
    assert events[0]["event_type"] == "run.failed"
    assert events[0]["status"] == "failed"



def test_quote_runtime_metrics_score_validation_comparison_and_reconciliation():
    from harness_telemetry import build_quote_evaluation_metrics

    metrics = build_quote_evaluation_metrics({
        "status": "success",
        "metrics": {"document_count": 2, "quotation_count": 2},
        "validation": [
            {"completeness_score": 100.0, "missing_fields": []},
            {"completeness_score": 75.0, "missing_fields": ["warranty"]},
        ],
        "scores": [
            {"score": 85.0},
            {"score": None},
        ],
        "risks": [
            {"supplier": "Private Supplier A", "items": ["Private warranty risk"]},
            {"supplier": "Private Supplier B", "items": []},
        ],
        "price_anomalies": [{"supplier": "Private Supplier", "detail": "private anomaly"}],
        "comparison_matrix": {
            "cost_comparable": True,
            "line_items": [
                {"unit_price_comparable": True},
                {"unit_price_comparable": False},
            ],
            "pricing_reconciliation": [
                {"status": "matched"},
                {"status": "review"},
                {"status": "partial_check"},
            ],
        },
        "analysis": {"status": "success", "analysis": {"overall_recommendation": "private analysis"}},
        "recommendation": {
            "status": "success",
            "primary_recommendation": {"supplier": "Private Supplier"},
        },
    })

    assert metrics["procurement.document_count"] == 2
    assert metrics["procurement.quote_count"] == 2
    assert metrics["runtime.extraction_completeness"] == 0.875
    assert metrics["runtime.quotation_validation_pass_rate"] == 0.5
    assert metrics["runtime.scoring_coverage"] == 0.5
    assert metrics["runtime.cost_comparability"] == 1.0
    assert metrics["runtime.comparable_line_item_rate"] == 0.5
    assert metrics["runtime.price_reconciliation_coverage"] == 0.666667
    assert metrics["runtime.price_reconciliation_match_rate"] == 0.5
    assert metrics["runtime.price_reconciliation_review_rate"] == 0.5
    assert metrics["runtime.risk_finding_count"] == 1
    assert metrics["runtime.risked_quotation_rate"] == 0.5
    assert metrics["runtime.price_anomaly_count"] == 1
    assert metrics["runtime.analysis_available"] == 1.0
    assert metrics["runtime.recommendation_available"] == 1.0
    serialized = str(metrics)
    assert "Private Supplier" not in serialized
    assert "Private warranty risk" not in serialized
    assert "private anomaly" not in serialized
    assert "private analysis" not in serialized


def test_quote_telemetry_adds_bounded_experiment_lineage(monkeypatch):
    import json

    import harness_telemetry

    monkeypatch.setenv("EVALUATION_HARNESS_URL", "https://example.invalid")
    monkeypatch.setenv("EVALUATION_HARNESS_INGEST_TOKEN", "quotesense-test-token")
    monkeypatch.setenv("EVALUATION_EXPERIMENT_ID", "quotesense-v2")
    monkeypatch.setenv("EVALUATION_DATASET_VERSION", "synthetic-quotes-v3")
    monkeypatch.setenv("EVALUATION_CONFIG_VERSION", "procurement-weights-v1")
    sent = {}

    class FakeResponse:
        status = 202

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_urlopen(request, timeout):
        sent["payload"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse()

    monkeypatch.setattr(harness_telemetry, "urlopen", fake_urlopen)
    assert harness_telemetry.record_event(
        event_type="evaluation.completed",
        status="success",
        workflow="quotation_analysis",
        experiment_id="quotesense-v2",
        dataset_version="synthetic-quotes-v3",
        config_version="procurement-weights-v1",
        metrics={"external.test.metric": 0.9},
    )
    payload = sent["payload"]
    assert payload["experiment_id"] == "quotesense-v2"
    assert payload["dataset_version"] == "synthetic-quotes-v3"
    assert payload["config_version"] == "procurement-weights-v1"
    assert payload["metrics"] == {"external.test.metric": 0.9}
