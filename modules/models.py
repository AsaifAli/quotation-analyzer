"""Validated domain models and tolerant normalization for LLM extraction output."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class EvidenceRef(BaseModel):
    source: str
    location: str
    excerpt: str = ""


class Quotation(BaseModel):
    model_config = ConfigDict(extra="ignore")
    supplier: Optional[str] = None
    project_description: Optional[str] = None
    total_cost: Optional[float] = None
    currency: Optional[str] = None
    key_features: List[str] = Field(default_factory=list)
    terms_conditions: Optional[str] = None
    validity_period: Optional[str] = None
    delivery_timeline: Optional[str] = None
    contact_info: Optional[str] = None
    evidence: List[EvidenceRef] = Field(default_factory=list)


class ExtractionResult(BaseModel):
    quotations: List[Quotation] = Field(default_factory=list)


class Recommendation(BaseModel):
    supplier: Optional[str] = None
    reason: str = ""
    confidence: str = "low"


class RecommendationResult(BaseModel):
    primary_recommendation: Recommendation = Field(default_factory=Recommendation)
    alternatives: List[Recommendation] = Field(default_factory=list)
    risk_assessment: List[str] = Field(default_factory=list)
    action_items: List[str] = Field(default_factory=list)


class AnalysisResult(BaseModel):
    comparison: List[dict] = Field(default_factory=list)
    overall_recommendation: str = ""
    confidence: str = "low"
    risks: List[str] = Field(default_factory=list)
    next_steps: List[str] = Field(default_factory=list)


# These are generic semantic aliases, not supplier/document-specific rules.
_FIELD_ALIASES = {
    "supplier": ("supplier", "vendor", "provider", "company", "bidder", "seller", "name"),
    "project_description": ("project_description", "description", "scope", "project", "work_description"),
    "total_cost": ("total_cost", "total_amount", "quoted_amount", "grand_total", "total", "amount", "price", "cost"),
    "currency": ("currency", "currency_code", "currency_symbol"),
    "key_features": ("key_features", "features", "deliverables", "scope_items", "included_items"),
    "terms_conditions": ("terms_conditions", "terms", "conditions", "payment_terms"),
    "validity_period": ("validity_period", "validity", "quote_validity", "offer_validity"),
    "delivery_timeline": ("delivery_timeline", "delivery", "timeline", "lead_time", "delivery_period"),
    "contact_info": ("contact_info", "contact", "contact_details", "representative"),
}

_CURRENCY_SYMBOLS = {
    "₹": "INR", "₨": "INR", "$": "USD", "€": "EUR", "£": "GBP", "¥": "JPY",
    "₩": "KRW", "₽": "RUB", "₺": "TRY", "₫": "VND", "฿": "THB", "₦": "NGN",
    "₱": "PHP", "₴": "UAH", "₪": "ILS", "₡": "CRC", "₲": "PYG", "₵": "GHS",
}


def _first(mapping: Dict[str, Any], aliases: tuple[str, ...]) -> Any:
    for key in aliases:
        if key in mapping and mapping[key] not in (None, "", [], {}):
            return mapping[key]
    return None


def _stringify(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, dict):
        for key in ("name", "value", "text", "label", "code"):
            if value.get(key) not in (None, ""):
                return str(value[key]).strip()
        return ", ".join(f"{k}: {v}" for k, v in value.items()) or None
    if isinstance(value, list):
        return ", ".join(str(v) for v in value if v not in (None, "")) or None
    return str(value).strip() or None


def _listify(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [x for x in (_stringify(v) for v in value) if x]
    if isinstance(value, dict):
        value = value.get("items") or value.get("values") or value.get("value") or value
    if isinstance(value, str):
        parts = re.split(r"\s*(?:;|\n|•|\u2022)\s*", value)
        return [p.strip(" -\t") for p in parts if p.strip(" -\t")]
    return [str(value)]


def _extract_amount(value: Any) -> tuple[Optional[float], Optional[str]]:
    """Convert common money representations to a numeric amount and currency code."""
    detected_currency = None
    if isinstance(value, dict):
        detected_currency = _stringify(value.get("currency") or value.get("currency_code") or value.get("code"))
        value = value.get("amount") or value.get("value") or value.get("total") or value.get("price")
    if value is None:
        return None, detected_currency
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value), detected_currency

    text = str(value).strip()
    for symbol, code in _CURRENCY_SYMBOLS.items():
        if symbol in text:
            detected_currency = detected_currency or code
            text = text.replace(symbol, " ")
            break

    # Prefer explicit ISO-like currency codes if present.
    code_match = re.search(r"\b([A-Z]{3})\b", text.upper())
    if code_match:
        detected_currency = detected_currency or code_match.group(1)

    numbers = re.findall(r"[-+]?\d[\d\s,]*(?:\.\d+)?", text)
    if not numbers:
        return None, detected_currency
    number = numbers[-1].replace(" ", "")
    # Handle either 1,234.56 or 1.234,56 without assuming a particular locale.
    if "," in number and "." in number:
        if number.rfind(",") > number.rfind("."):
            number = number.replace(".", "").replace(",", ".")
        else:
            number = number.replace(",", "")
    elif "," in number:
        tail = number.rsplit(",", 1)[-1]
        number = number.replace(",", ".") if len(tail) in (1, 2) else number.replace(",", "")
    try:
        return float(number), detected_currency
    except ValueError:
        return None, detected_currency


def _unwrap_records(payload: Any) -> List[Dict[str, Any]]:
    """Accept canonical objects, bare arrays, and single-record objects from imperfect LLMs."""
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("quotations", "quotes", "results", "items", "records", "data"):
        candidate = payload.get(key)
        if isinstance(candidate, list):
            return [x for x in candidate if isinstance(x, dict)]
    if any(_first(payload, aliases) is not None for aliases in _FIELD_ALIASES.values()):
        return [payload]
    return []


def normalize_extraction_payload(payload: Any) -> Dict[str, Any]:
    """Normalize varied LLM JSON shapes into the canonical ExtractionResult shape."""
    normalized = []
    for raw in _unwrap_records(payload):
        amount, detected_currency = _extract_amount(_first(raw, _FIELD_ALIASES["total_cost"]))
        currency_value = _first(raw, _FIELD_ALIASES["currency"]) or detected_currency
        normalized.append({
            "supplier": _stringify(_first(raw, _FIELD_ALIASES["supplier"])),
            "project_description": _stringify(_first(raw, _FIELD_ALIASES["project_description"])),
            "total_cost": amount,
            "currency": _stringify(currency_value),
            "key_features": _listify(_first(raw, _FIELD_ALIASES["key_features"])),
            "terms_conditions": _stringify(_first(raw, _FIELD_ALIASES["terms_conditions"])),
            "validity_period": _stringify(_first(raw, _FIELD_ALIASES["validity_period"])),
            "delivery_timeline": _stringify(_first(raw, _FIELD_ALIASES["delivery_timeline"])),
            "contact_info": _stringify(_first(raw, _FIELD_ALIASES["contact_info"])),
        })
    return {"quotations": normalized}


def _unwrap_object(payload: Any, preferred_keys: tuple[str, ...]) -> Dict[str, Any]:
    """Find the first object matching a generic response envelope."""
    if isinstance(payload, dict):
        for key in preferred_keys:
            value = payload.get(key)
            if isinstance(value, dict):
                return value
        return payload
    if isinstance(payload, list):
        return {"items": payload}
    return {}


def normalize_analysis_payload(payload: Any) -> Dict[str, Any]:
    """Normalize common model envelopes before validating the analysis result."""
    raw = _unwrap_object(payload, ("analysis", "result", "data", "response"))
    comparison = raw.get("comparison", raw.get("comparisons", raw.get("items", [])))
    if not isinstance(comparison, list):
        comparison = [comparison] if isinstance(comparison, dict) else []
    return {
        "comparison": comparison,
        "overall_recommendation": _stringify(raw.get("overall_recommendation") or raw.get("recommendation") or raw.get("summary")) or "",
        "confidence": _stringify(raw.get("confidence") or raw.get("confidence_level")) or "low",
        "risks": _listify(raw.get("risks") or raw.get("risk")),
        "next_steps": _listify(raw.get("next_steps") or raw.get("actions") or raw.get("action_items")),
    }


def normalize_recommendation_payload(payload: Any) -> Dict[str, Any]:
    """Normalize common recommendation envelopes without supplier-specific rules."""
    raw = _unwrap_object(payload, ("recommendation", "recommendations", "result", "data", "response"))
    primary = raw.get("primary_recommendation") or raw.get("recommendation") or raw.get("winner") or {}
    if isinstance(primary, str):
        primary = {"supplier": primary, "reason": "", "confidence": "low"}
    if not isinstance(primary, dict):
        primary = {}
    alternatives = raw.get("alternatives") or raw.get("other_options") or []
    if isinstance(alternatives, dict):
        alternatives = [alternatives]
    if not isinstance(alternatives, list):
        alternatives = []
    cleaned_alternatives = []
    for item in alternatives:
        if isinstance(item, str):
            cleaned_alternatives.append({"supplier": item, "reason": "", "confidence": "low"})
        elif isinstance(item, dict):
            cleaned_alternatives.append(item)
    return {
        "primary_recommendation": primary,
        "alternatives": cleaned_alternatives,
        "risk_assessment": _listify(raw.get("risk_assessment") or raw.get("risks") or raw.get("risk")),
        "action_items": _listify(raw.get("action_items") or raw.get("next_steps") or raw.get("actions")),
    }
