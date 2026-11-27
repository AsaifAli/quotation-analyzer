from types import SimpleNamespace

from modules.ai_agent import AgentState, QuotationIntelligenceAgent


def _agent_with_synthetic_extraction(monkeypatch):
    agent = QuotationIntelligenceAgent.__new__(QuotationIntelligenceAgent)
    agent.llm = SimpleNamespace(provider="openai", model="test-model")
    agent.state = AgentState()
    agent.web_search = SimpleNamespace(search=lambda _query: [])
    quotation = {
        "supplier": "Example Supplier",
        "project_description": "Synthetic office supplies quotation",
        "total_cost": 100000,
        "currency": "INR",
        "key_features": ["Delivery", "Warranty"],
        "terms_conditions": "Net 30 days. Warranty included.",
        "validity_period": "30 days",
        "delivery_timeline": "14 days",
        "contact_info": "example.invalid",
        "warranty": "12 months",
    }

    monkeypatch.setattr(
        agent,
        "extract_document",
        lambda _path: {
            "source": "synthetic-source",
            "quotations": [quotation],
            "evidence": [{"source": "synthetic-source", "location": "page 1", "text": "Supplier quotation"}],
            "truncated": False,
            "characters": 120,
            "elapsed_seconds": 0.01,
        },
    )
    return agent


def test_processing_trace_emits_real_ordered_stages_and_returns_trace(monkeypatch):
    agent = _agent_with_synthetic_extraction(monkeypatch)
    events = []

    result = agent.process_documents(
        ["synthetic-quotation.txt"],
        query="extract",
        stage_callback=events.append,
    )

    stages = [(event["stage"], event["status"]) for event in events]
    assert stages == [
        ("extract", "started"),
        ("extract", "completed"),
        ("validation", "started"),
        ("validation", "completed"),
        ("scoring", "started"),
        ("scoring", "completed"),
        ("risk_assessment", "started"),
        ("risk_assessment", "completed"),
        ("complete", "completed"),
    ]
    assert result["processing_trace"] == events
    assert result["metrics"]["quotation_count"] == 1


def test_processing_trace_exposes_only_bounded_metrics_not_supplier_content(monkeypatch):
    agent = _agent_with_synthetic_extraction(monkeypatch)
    events = []

    agent.process_documents(
        ["private-supplier-name-confidential.pdf"],
        query="extract",
        stage_callback=events.append,
    )

    serialized = repr(events)
    assert "Example Supplier" not in serialized
    assert "private-supplier-name-confidential" not in serialized
    assert "Supplier quotation" not in serialized
    assert all("metrics" in event and isinstance(event["metrics"], dict) for event in events)
    assert events[-1]["metrics"]["quotation_count"] == 1
