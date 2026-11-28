"""Validated domain models and tolerant normalization for LLM extraction output."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class EvidenceRef(BaseModel):
    source: str
    location: str
    excerpt: str = ""


class QuotationLineItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    description: str
    quantity: Optional[float] = None
    unit: Optional[str] = None
    unit_price: Optional[float] = None
    total_price: Optional[float] = None
    notes: Optional[str] = None


class Quotation(BaseModel):
    model_config = ConfigDict(extra="ignore")
    supplier: Optional[str] = None
    quote_reference: Optional[str] = None
    quote_date: Optional[str] = None
    source_document: Optional[str] = None
    project_description: Optional[str] = None
    subtotal: Optional[float] = None
    tax_amount: Optional[float] = None
    tax_included: Optional[bool] = None
    shipping_cost: Optional[float] = None
    discount_amount: Optional[float] = None
    additional_charges: Optional[float] = None
    total_cost: Optional[float] = None
    currency: Optional[str] = None
    line_items: List[QuotationLineItem] = Field(default_factory=list)
    key_features: List[str] = Field(default_factory=list)
    payment_terms: Optional[str] = None
    warranty: Optional[str] = None
    support: Optional[str] = None
    exclusions: List[str] = Field(default_factory=list)
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
    "quote_reference": ("quote_reference", "quotation_number", "quote_number", "reference", "proposal_number"),
    "quote_date": ("quote_date", "quotation_date", "date_issued", "issue_date"),
    "subtotal": ("subtotal", "sub_total", "net_amount", "base_amount"),
    "tax_amount": ("tax_amount", "tax", "gst_amount", "vat_amount"),
    "tax_included": ("tax_included", "includes_tax", "gst_inclusive", "vat_inclusive"),
    "shipping_cost": ("shipping_cost", "freight", "delivery_charge", "shipping", "transportation"),
    "discount_amount": ("discount_amount", "discount", "rebate"),
    "additional_charges": ("additional_charges", "other_charges", "misc_charges", "handling_charges"),
    "payment_terms": ("payment_terms", "payment_schedule", "payment_conditions"),
    "warranty": ("warranty", "warranty_period", "guarantee"),
    "support": ("support", "maintenance", "service_support", "after_sales_support"),
    "exclusions": ("exclusions", "not_included", "out_of_scope", "excluded_items"),
    "line_items": ("line_items", "itemized_details", "pricing_table", "bill_of_quantities", "boq"),
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


def _normalize_line_items(value: Any) -> List[Dict[str, Any]]:
    """Normalize itemized quote rows without guessing missing amounts or units."""
    if isinstance(value, dict):
        value = value.get("items") or value.get("rows") or value.get("line_items") or []
    if not isinstance(value, list):
        return []

    normalized = []
    for item in value:
        if isinstance(item, str):
            item = {"description": item}
        if not isinstance(item, dict):
            continue
        description = _stringify(
            _first(item, ("description", "item", "product", "service", "name", "scope"))
        )
        if not description:
            continue
        quantity = _extract_amount(
            _first(item, ("quantity", "qty", "count"))
        )[0]
        unit_price = _extract_amount(
            _first(item, ("unit_price", "rate", "price_per_unit", "unit_rate"))
        )[0]
        total_price = _extract_amount(
            _first(item, ("total_price", "line_total", "amount", "total", "extended_price"))
        )[0]
        normalized.append({
            "description": description[:240],
            "quantity": quantity,
            "unit": _stringify(_first(item, ("unit", "uom", "measurement_unit"))),
            "unit_price": unit_price,
            "total_price": total_price,
            "notes": _stringify(_first(item, ("notes", "remarks", "specification", "details"))),
        })
    return normalized


def _normalize_tax_included(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"true", "yes", "included", "inclusive", "gst inclusive", "vat inclusive"}:
        return True
    if text in {"false", "no", "excluded", "exclusive", "gst extra", "vat extra"}:
        return False
    return None


def _unwrap_records(payload: Any) -> List[Dict[str, Any]]:
    """Accept canonical objects, bare arrays, and single-record objects from imperfect LLMs."""
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if not isinstance(payload, dict):
        return []
    # A single quotation may itself contain an "items" line-item array.
    # Recognize the quotation envelope before looking for outer record lists.
    if any(_first(payload, aliases) is not None for aliases in _FIELD_ALIASES.values()):
        return [payload]
    for key in ("quotations", "quotes", "results", "items", "records", "data"):
        candidate = payload.get(key)
        if isinstance(candidate, list):
            return [x for x in candidate if isinstance(x, dict)]
    return []


def normalize_extraction_payload(payload: Any) -> Dict[str, Any]:
    """Normalize varied LLM JSON shapes into the canonical ExtractionResult shape."""
    normalized = []
    for raw in _unwrap_records(payload):
        amount, detected_currency = _extract_amount(_first(raw, _FIELD_ALIASES["total_cost"]))
        currency_value = _first(raw, _FIELD_ALIASES["currency"]) or detected_currency

        numeric_fields = {}
        for field in (
            "subtotal", "tax_amount", "shipping_cost",
            "discount_amount", "additional_charges",
        ):
            numeric_fields[field] = _extract_amount(
                _first(raw, _FIELD_ALIASES[field])
            )[0]

        normalized.append({
            "supplier": _stringify(_first(raw, _FIELD_ALIASES["supplier"])),
            "quote_reference": _stringify(_first(raw, _FIELD_ALIASES["quote_reference"])),
            "quote_date": _stringify(_first(raw, _FIELD_ALIASES["quote_date"])),
            "project_description": _stringify(_first(raw, _FIELD_ALIASES["project_description"])),
            **numeric_fields,
            "tax_included": _normalize_tax_included(
                _first(raw, _FIELD_ALIASES["tax_included"])
            ),
            "total_cost": amount,
            "currency": _stringify(currency_value),
            "line_items": _normalize_line_items(_first(raw, _FIELD_ALIASES["line_items"])),
            "key_features": _listify(_first(raw, _FIELD_ALIASES["key_features"])),
            "payment_terms": _stringify(_first(raw, _FIELD_ALIASES["payment_terms"])),
            "warranty": _stringify(_first(raw, _FIELD_ALIASES["warranty"])),
            "support": _stringify(_first(raw, _FIELD_ALIASES["support"])),
            "exclusions": _listify(_first(raw, _FIELD_ALIASES["exclusions"])),
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
