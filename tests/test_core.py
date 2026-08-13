import os, tempfile
from modules.document_processor import DocumentProcessor
from modules.scoring import validate_quotations, score_quotations
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
