"""Deterministic, configurable procurement scoring and risk detection."""
from typing import Any, Dict, List
from .models import Quotation

REQUIRED_FIELDS = [
    "supplier", "project_description", "total_cost", "currency",
    "key_features", "terms_conditions", "validity_period",
    "delivery_timeline", "contact_info"
]
DEFAULT_WEIGHTS = {"cost": 0.40, "completeness": 0.25, "timeline": 0.15, "terms": 0.10, "risk": 0.10}

def _num(value):
    try: return float(value)
    except (TypeError, ValueError): return None

def normalize_weights(weights: Dict[str, float] | None = None) -> Dict[str, float]:
    raw = dict(DEFAULT_WEIGHTS)
    if weights:
        raw.update({k: float(v) for k, v in weights.items() if k in raw and float(v) >= 0})
    total = sum(raw.values()) or 1.0
    return {k: round(v / total, 6) for k, v in raw.items()}

def validate_quotations(quotations: List[Dict[str, Any]] | List[Quotation]) -> List[Dict[str, Any]]:
    results = []
    for raw in quotations:
        q = raw.model_dump() if isinstance(raw, Quotation) else raw
        present = [f for f in REQUIRED_FIELDS if q.get(f) not in (None, "", [], {})]
        results.append({
            "supplier": q.get("supplier") or "Unknown",
            "present_fields": present,
            "missing_fields": [f for f in REQUIRED_FIELDS if f not in present],
            "completeness_score": round(len(present) / len(REQUIRED_FIELDS) * 100, 1),
        })
    return results

def _timeline_score(value: str | None) -> float | None:
    if not value: return None
    text = value.lower()
    import re
    m = re.search(r"(\d+(?:\.\d+)?)\s*(day|days|week|weeks|month|months)", text)
    if not m: return 50.0
    n, unit = float(m.group(1)), m.group(2)
    days = n * (30 if "month" in unit else 7 if "week" in unit else 1)
    return max(0.0, min(100.0, 100.0 * (1 - days / 180.0)))

def _terms_score(q: Dict[str, Any]) -> float:
    text = " ".join(str(q.get(k) or "") for k in ["terms_conditions", "validity_period"])
    score = 100.0 if text else 0.0
    if "100% upfront" in text.lower() or "full payment upfront" in text.lower(): score -= 35
    if "warranty" not in text.lower(): score -= 10
    return max(0.0, score)

def detect_risks(quotations: List[Dict[str, Any]], scores: List[Dict[str, Any]] | None = None) -> List[Dict[str, Any]]:
    risks = []
    for q in quotations:
        supplier = q.get("supplier") or "Unknown"
        text = " ".join(str(q.get(k) or "") for k in ["terms_conditions", "validity_period", "delivery_timeline"]).lower()
        items = []
        if not q.get("warranty") and "warranty" not in text: items.append(("medium", "Warranty information is missing."))
        if "100% upfront" in text or "full payment upfront" in text: items.append(("high", "Full upfront payment is stated."))
        if not q.get("delivery_timeline"): items.append(("medium", "Delivery timeline is missing."))
        if not q.get("validity_period"): items.append(("low", "Quotation validity period is missing."))
        if not q.get("terms_conditions"): items.append(("medium", "Terms and conditions are missing."))
        risks.append({"supplier": supplier, "level": "high" if any(x[0] == "high" for x in items) else "medium" if any(x[0] == "medium" for x in items) else "low", "items": [x[1] for x in items]})
    return risks

def detect_price_anomalies(quotations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Flag unusually high/low prices only when currencies are comparable."""
    values=[_num(q.get("total_cost")) for q in quotations]
    currencies={str(q.get("currency")).upper() for q in quotations if q.get("currency")}
    if len(currencies) > 1: return []
    valid=[v for v in values if v is not None]
    if len(valid) < 3: return []
    import statistics
    median=statistics.median(valid)
    if median == 0: return []
    out=[]
    for q,v in zip(quotations,values):
        if v is None: continue
        deviation=(v-median)/median*100
        if abs(deviation) >= 50:
            out.append({"supplier":q.get("supplier") or "Unknown","total_cost":v,"median_cost":median,"deviation_percent":round(deviation,1),"direction":"high" if deviation>0 else "low"})
    return out

def score_quotations(quotations: List[Dict[str, Any]], weights: Dict[str, float] | None = None) -> List[Dict[str, Any]]:
    weights = normalize_weights(weights)
    costs = [_num(q.get("total_cost")) for q in quotations]
    valid_costs = [c for c in costs if c is not None]
    currencies = {str(q.get("currency")).upper() for q in quotations if q.get("currency")}
    comparable_costs = len(currencies) <= 1
    min_cost, max_cost = (min(valid_costs), max(valid_costs)) if valid_costs and comparable_costs else (None, None)
    validation = validate_quotations(quotations)
    by_supplier = {v["supplier"]: v for v in validation}
    results = []
    for q, cost in zip(quotations, costs):
        supplier = q.get("supplier") or "Unknown"
        completeness = by_supplier[supplier]["completeness_score"]
        cost_score = None if min_cost is None or cost is None else (100.0 if max_cost == min_cost else 100 * (max_cost - cost) / (max_cost - min_cost))
        timeline = _timeline_score(q.get("delivery_timeline"))
        terms = _terms_score(q)
        risk_penalty = 0.0
        text = str(q.get("terms_conditions") or "").lower()
        if "100% upfront" in text or "full payment upfront" in text: risk_penalty += 35
        if not q.get("warranty") and "warranty" not in text: risk_penalty += 10
        risk_score = max(0.0, 100.0 - risk_penalty)
        components = {"cost": cost_score, "completeness": completeness, "timeline": timeline, "terms": terms, "risk": risk_score}
        available = [(k, v) for k, v in components.items() if v is not None]
        denom = sum(weights[k] for k, _ in available) or 1.0
        score = round(sum(weights[k] * v for k, v in available) / denom, 1) if available else None
        results.append({"supplier": supplier, "score": score, "cost_score": round(cost_score,1) if cost_score is not None else None,
                        "completeness_score": completeness, "timeline_score": round(timeline,1) if timeline is not None else None,
                        "terms_score": round(terms,1), "risk_score": round(risk_score,1), "currency": q.get("currency"),
                        "total_cost": cost, "missing_fields": by_supplier[supplier]["missing_fields"],
                        "weights": weights, "cost_comparable": comparable_costs})
    return sorted(results, key=lambda x: x["score"] if x["score"] is not None else -1, reverse=True)
