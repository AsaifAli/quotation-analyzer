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



def test_opt_in_market_context_is_reported_as_a_separate_real_stage(monkeypatch):
    agent = _agent_with_synthetic_extraction(monkeypatch)
    events = []
    monkeypatch.setattr(
        agent,
        "market_insights",
        lambda scope=None: {
            "status": "success",
            "query": f"procurement pricing benchmark {scope}",
            "insights": {"status": "success", "results": [{"title": "Example source"}]},
        },
    )
    result = agent.process_documents(
        ["synthetic-quotation.txt"],
        query="extract",
        do_market=True,
        market_query="office chairs",
        stage_callback=events.append,
    )
    market_events = [event for event in events if event["stage"] == "market_research"]
    assert [event["status"] for event in market_events] == ["started", "completed"]
    assert market_events[-1]["metrics"] == {"result_count": 1, "available": True}
    assert result["market"]["query"].endswith("office chairs")


def test_optional_market_search_failure_does_not_fail_quote_workflow(monkeypatch):
    agent = _agent_with_synthetic_extraction(monkeypatch)

    def fail_search(_query):
        raise RuntimeError("synthetic provider failure")

    agent.web_search.search = fail_search
    market = agent.market_insights(scope="office chairs")
    assert market["status"] == "success"
    assert market["insights"]["status"] == "unavailable"
    assert "could not be retrieved" in market["insights"]["message"]
