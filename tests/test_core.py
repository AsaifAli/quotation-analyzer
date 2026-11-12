import math
import os, tempfile
from modules.document_processor import DocumentProcessor
from modules.scoring import (
    validate_quotations,
    score_quotations,
    detect_price_anomalies,
    count_risk_findings,
)
from modules.llm_provider import extract_json

def test_text_ingestion():
    fd, path = tempfile.mkstemp(suffix=".txt")
    try:
        os.write(fd, b"Supplier: Example\nCost: 1000")
        os.close(fd)
        assert "Example" in DocumentProcessor().extract_text(path)
    finally:
        if os.path.exists(path): os.unlink(path)

def test_validation():
    result = validate_quotations([{"supplier":"A","total_cost":100,"currency":"USD"}])
    assert result[0]["completeness_score"] > 0
    assert "terms_conditions" in result[0]["missing_fields"]

def test_deterministic_scoring():
    quotes=[{"supplier":"A","total_cost":100,"currency":"USD","project_description":"x"},
            {"supplier":"B","total_cost":200,"currency":"USD","project_description":"x"}]
    result=score_quotations(quotes)
    assert result[0]["supplier"]=="A"
    assert result[0]["score"] is not None

def test_json_extraction():
    assert extract_json('```json\n{"ok": true}\n```') == {"ok": True}

from modules.models import ExtractionResult, normalize_extraction_payload


def test_normalizes_bare_quotation_array_and_money_string():
    payload = [{
        "supplier": {"name": "Example Vendor"},
        "total_cost": "₹ 370.40",
        "description": "Sample proposal",
    }]
    result = ExtractionResult.model_validate(normalize_extraction_payload(payload))
    assert len(result.quotations) == 1
    assert result.quotations[0].supplier == "Example Vendor"
    assert result.quotations[0].total_cost == 370.40
    assert result.quotations[0].currency == "INR"


def test_normalizes_single_record_without_wrapper():
    payload = {"vendor": "Vendor A", "amount": "USD 1,250.50"}
    result = ExtractionResult.model_validate(normalize_extraction_payload(payload))
    assert result.quotations[0].supplier == "Vendor A"
    assert result.quotations[0].total_cost == 1250.50
    assert result.quotations[0].currency == "USD"


def test_provider_accepts_dict_or_list_json_without_shape_assumptions():
    from modules.llm_provider import extract_json
    assert extract_json('{"items": [{"name": "A"}]}')["items"][0]["name"] == "A"
    assert extract_json('[{"name": "A"}]')[0]["name"] == "A"


def test_analysis_and_recommendation_normalization():
    from modules.models import normalize_analysis_payload, normalize_recommendation_payload
    analysis = normalize_analysis_payload({"result": {"recommendation": "A", "risk": "missing warranty", "actions": "review terms"}})
    assert analysis["overall_recommendation"] == "A"
    assert analysis["risks"] == ["missing warranty"]
    recommendation = normalize_recommendation_payload({"winner": "A", "risks": ["review terms"]})
    assert recommendation["primary_recommendation"]["supplier"] == "A"


def test_gemini_schema_normalizes_union_types():
    from modules.llm_provider import _gemini_compatible_schema
    import config

    schema = _gemini_compatible_schema(config.QUOTATION_SCHEMA)
    quotation = schema["properties"]["quotations"]["items"]
    assert quotation["properties"]["supplier"]["type"] == "string"
    assert quotation["properties"]["total_cost"]["type"] == "string"
    assert "additionalProperties" not in quotation


def test_extract_json_handles_array_and_object():
    from modules.llm_provider import extract_json

    assert extract_json('[{"supplier":"A"}]')[0]["supplier"] == "A"
    assert extract_json('```json\n{"quotations":[]}\n```') == {"quotations": []}


def test_gemini_schema_removes_additional_properties_at_all_levels():
    from modules.llm_provider import _gemini_compatible_schema

    schema = {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {"type": "object", "additionalProperties": True},
            }
        },
        "additionalProperties": False,
    }
    converted = _gemini_compatible_schema(schema)
    assert "additionalProperties" not in converted
    assert "additionalProperties" not in converted["properties"]["items"]["items"]


def test_pdf_text_ingestion(tmp_path):
    import pymupdf

    path = tmp_path / "quotation.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Supplier: PDF Example")
    doc.save(str(path))
    doc.close()

    result = DocumentProcessor().extract(str(path))
    assert "PDF Example" in result["text"]
    assert result["evidence"][0]["kind"] == "text"


def test_scanned_pdf_ocr(tmp_path, monkeypatch):
    import io
    import pymupdf
    import config
    from PIL import Image, ImageDraw, ImageFont

    monkeypatch.setattr(config, "OCR_ENABLED", True)

    image = Image.new("RGB", (1600, 300), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=90)
    draw.text((60, 90), "QUOTESENSE OCR TEST 12345", fill="black", font=font)

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")

    path = tmp_path / "scanned.pdf"
    doc = pymupdf.open()
    page = doc.new_page(width=800, height=150)
    page.insert_image(page.rect, stream=buffer.getvalue())
    doc.save(str(path))
    doc.close()

    result = DocumentProcessor().extract(str(path))

    assert "QUOTESENSE" in result["text"].upper()
    assert result["evidence"][0]["kind"] == "ocr"


def test_cost_scoring_requires_matching_explicit_currency():
    quotes = [
        {"supplier": "A", "total_cost": 100, "currency": "USD"},
        {"supplier": "B", "total_cost": 200, "currency": "usd"},
    ]

    scores = score_quotations(quotes)

    assert all(item["cost_comparable"] for item in scores)
    assert all(item["cost_score"] is not None for item in scores)
    assert "USD" in scores[0]["cost_comparability_reason"]


def test_cost_scoring_excluded_when_currency_missing():
    quotes = [
        {"supplier": "A", "total_cost": 100, "currency": "USD"},
        {"supplier": "B", "total_cost": 200, "currency": None},
    ]

    scores = score_quotations(quotes)

    assert all(item["cost_comparable"] is False for item in scores)
    assert all(item["cost_score"] is None for item in scores)
    assert "no explicit currency" in (
        scores[0]["cost_comparability_reason"]
    )


def test_cost_scoring_excluded_for_mixed_currencies():
    quotes = [
        {"supplier": "A", "total_cost": 100, "currency": "USD"},
        {"supplier": "B", "total_cost": 200, "currency": "INR"},
    ]

    scores = score_quotations(quotes)

    assert all(item["cost_comparable"] is False for item in scores)
    assert all(item["cost_score"] is None for item in scores)
    assert "different currencies" in (
        scores[0]["cost_comparability_reason"]
    )


def test_price_anomalies_require_comparable_currencies():
    mixed_quotes = [
        {"supplier": "A", "total_cost": 100, "currency": "USD"},
        {"supplier": "B", "total_cost": 110, "currency": "USD"},
        {"supplier": "C", "total_cost": 400, "currency": None},
    ]

    assert detect_price_anomalies(mixed_quotes) == []

    comparable_quotes = [
        {"supplier": "A", "total_cost": 100, "currency": "USD"},
        {"supplier": "B", "total_cost": 110, "currency": "USD"},
        {"supplier": "C", "total_cost": 400, "currency": "USD"},
    ]

    anomalies = detect_price_anomalies(comparable_quotes)

    assert len(anomalies) == 1
    assert anomalies[0]["supplier"] == "C"
    assert anomalies[0]["direction"] == "high"


def test_risk_counter_ignores_empty_supplier_records():
    risks = [
        {"supplier": "A", "items": []},
        {"supplier": "B", "items": ["Missing warranty", "", None]},
        {"supplier": "C", "items": "Full upfront payment"},
    ]

    assert count_risk_findings(risks) == 2


def test_non_finite_prices_are_excluded_from_cost_scoring():
    quotes = [
        {"supplier": "A", "total_cost": float("nan"), "currency": "USD"},
        {"supplier": "B", "total_cost": 100, "currency": "USD"},
        {"supplier": "C", "total_cost": 110, "currency": "USD"},
        {"supplier": "D", "total_cost": 400, "currency": "USD"},
    ]

    scores = score_quotations(quotes)
    by_supplier = {item["supplier"]: item for item in scores}

    assert by_supplier["A"]["total_cost"] is None
    assert by_supplier["A"]["cost_score"] is None
    assert by_supplier["B"]["cost_score"] == 100.0
    assert by_supplier["D"]["cost_score"] == 0.0
    assert all(
        item["score"] is None or math.isfinite(item["score"])
        for item in scores
    )


def test_non_finite_prices_do_not_break_price_anomaly_detection():
    quotes = [
        {"supplier": "A", "total_cost": float("inf"), "currency": "USD"},
        {"supplier": "B", "total_cost": 100, "currency": "USD"},
        {"supplier": "C", "total_cost": 110, "currency": "USD"},
        {"supplier": "D", "total_cost": 400, "currency": "USD"},
    ]

    anomalies = detect_price_anomalies(quotes)

    assert len(anomalies) == 1
    assert anomalies[0]["supplier"] == "D"


def test_normalize_weights_ignores_invalid_and_non_finite_overrides():
    from modules.scoring import normalize_weights

    weights = normalize_weights(
        {
            "cost": float("inf"),
            "timeline": "not-a-number",
            "risk": 0.2,
        }
    )

    expected_total = 0.40 + 0.25 + 0.15 + 0.10 + 0.20
    assert weights["cost"] == round(0.40 / expected_total, 6)
    assert weights["timeline"] == round(0.15 / expected_total, 6)
    assert weights["risk"] == round(0.20 / expected_total, 6)
    assert abs(sum(weights.values()) - 1.0) < 1e-5


def test_scoring_keeps_duplicate_supplier_validation_records_distinct():
    quotes = [
        {"supplier": "Same Supplier", "total_cost": 100, "currency": "USD"},
        {
            "supplier": "Same Supplier",
            "total_cost": 200,
            "currency": "USD",
            "project_description": "Complete quotation",
            "key_features": ["Feature"],
            "terms_conditions": "Warranty included",
            "validity_period": "30 days",
            "delivery_timeline": "10 days",
            "contact_info": "sales@example.com",
        },
    ]

    scores = score_quotations(quotes)
    completeness = sorted(item["completeness_score"] for item in scores)

    assert completeness[0] < completeness[1]
