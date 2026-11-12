"""Deterministic, configurable procurement scoring and risk detection."""

from __future__ import annotations

import math
import re
import statistics
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from .models import Quotation

REQUIRED_FIELDS = [
    "supplier",
    "project_description",
    "total_cost",
    "currency",
    "key_features",
    "terms_conditions",
    "validity_period",
    "delivery_timeline",
    "contact_info",
]

DEFAULT_WEIGHTS: dict[str, float] = {
    "cost": 0.40,
    "completeness": 0.25,
    "timeline": 0.15,
    "terms": 0.10,
    "risk": 0.10,
}

QuotationInput = Mapping[str, Any] | Quotation


def _num(value: Any) -> float | None:
    """Convert a value to a finite float; reject NaN and infinities."""
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _cost_comparability(
    quotations: Sequence[Mapping[str, Any]],
) -> tuple[bool, str]:
    """Allow price comparisons only when priced quotes share a known currency."""
    priced: list[tuple[float, str]] = []

    for quotation in quotations:
        amount = _num(quotation.get("total_cost"))
        if amount is None:
            continue

        currency = str(quotation.get("currency") or "").strip().upper()
        priced.append((amount, currency))

    if len(priced) < 2:
        return (
            False,
            "At least two supplier quotations with numeric prices are required.",
        )

    if any(not currency for _, currency in priced):
        return (
            False,
            "At least one priced quotation has no explicit currency. "
            "Cost scoring is excluded to avoid comparing unlike amounts.",
        )

    currencies = {currency for _, currency in priced}
    if len(currencies) != 1:
        return (
            False,
            "Priced quotations use different currencies "
            f"({', '.join(sorted(currencies))}). "
            "Cost scoring is excluded because no currency conversion is performed.",
        )

    currency = next(iter(currencies))
    return (
        True,
        f"All {len(priced)} priced quotations use the same currency ({currency}).",
    )


def normalize_weights(
    weights: Mapping[str, Any] | None = None,
) -> dict[str, float]:
    """Normalize known non-negative finite weights; ignore invalid overrides."""
    raw = dict(DEFAULT_WEIGHTS)
    if weights:
        for key, value in weights.items():
            if key not in raw:
                continue
            parsed = _num(value)
            if parsed is not None and parsed >= 0:
                raw[key] = parsed

    total = sum(raw.values()) or 1.0
    return {key: round(value / total, 6) for key, value in raw.items()}


def validate_quotations(
    quotations: Sequence[QuotationInput],
) -> list[dict[str, Any]]:
    """Return required-field coverage and missing-field details per quotation."""
    results: list[dict[str, Any]] = []

    for raw in quotations:
        quotation = raw.model_dump() if isinstance(raw, Quotation) else raw
        present = [
            field
            for field in REQUIRED_FIELDS
            if quotation.get(field) not in (None, "", [], {})
        ]
        results.append(
            {
                "supplier": quotation.get("supplier") or "Unknown",
                "present_fields": present,
                "missing_fields": [
                    field for field in REQUIRED_FIELDS if field not in present
                ],
                "completeness_score": round(
                    len(present) / len(REQUIRED_FIELDS) * 100,
                    1,
                ),
            }
        )

    return results


def _timeline_score(value: str | None) -> float | None:
    if not value:
        return None

    match = re.search(
        r"(\d+(?:\.\d+)?)\s*(day|days|week|weeks|month|months)",
        value.lower(),
    )
    if not match:
        return 50.0

    amount = _num(match.group(1))
    if amount is None:
        return 50.0

    unit = match.group(2)
    days = amount * (30 if "month" in unit else 7 if "week" in unit else 1)
    if not math.isfinite(days):
        return 0.0

    return max(0.0, min(100.0, 100.0 * (1 - days / 180.0)))


def _terms_score(quotation: Mapping[str, Any]) -> float:
    text = " ".join(
        str(quotation.get(key) or "")
        for key in ("terms_conditions", "validity_period")
    )
    score = 100.0 if text else 0.0
    lowered = text.lower()

    if "100% upfront" in lowered or "full payment upfront" in lowered:
        score -= 35
    if "warranty" not in lowered:
        score -= 10

    return max(0.0, score)


def detect_risks(
    quotations: Sequence[Mapping[str, Any]],
    scores: Sequence[Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Return supplier-specific missing-term and payment risks."""
    risks: list[dict[str, Any]] = []

    for quotation in quotations:
        supplier = quotation.get("supplier") or "Unknown"
        text = " ".join(
            str(quotation.get(key) or "")
            for key in ("terms_conditions", "validity_period", "delivery_timeline")
        ).lower()
        items: list[tuple[str, str]] = []

        if not quotation.get("warranty") and "warranty" not in text:
            items.append(("medium", "Warranty information is missing."))
        if "100% upfront" in text or "full payment upfront" in text:
            items.append(("high", "Full upfront payment is stated."))
        if not quotation.get("delivery_timeline"):
            items.append(("medium", "Delivery timeline is missing."))
        if not quotation.get("validity_period"):
            items.append(("low", "Quotation validity period is missing."))
        if not quotation.get("terms_conditions"):
            items.append(("medium", "Terms and conditions are missing."))

        level = (
            "high"
            if any(item[0] == "high" for item in items)
            else "medium"
            if any(item[0] == "medium" for item in items)
            else "low"
        )
        risks.append(
            {
                "supplier": supplier,
                "level": level,
                "items": [item[1] for item in items],
            }
        )

    return risks


def count_risk_findings(risks: Iterable[Mapping[str, Any]] | None) -> int:
    """Count actual non-empty findings, not empty supplier risk records."""
    count = 0

    for risk in risks or []:
        if not isinstance(risk, Mapping):
            continue

        items = risk.get("items") or []
        if isinstance(items, str):
            items = [items]
        if not isinstance(items, (list, tuple, set)):
            continue

        count += sum(
            1
            for item in items
            if item is not None and str(item).strip()
        )

    return count


def detect_price_anomalies(
    quotations: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Detect price outliers only when priced quotes share a known currency."""
    comparable, _ = _cost_comparability(quotations)
    if not comparable:
        return []

    values = [_num(quotation.get("total_cost")) for quotation in quotations]
    valid = [value for value in values if value is not None]
    if len(valid) < 3:
        return []

    median = statistics.median(valid)
    if median == 0:
        return []

    anomalies: list[dict[str, Any]] = []
    for quotation, value in zip(quotations, values):
        if value is None:
            continue

        deviation = (value - median) / median * 100
        if abs(deviation) >= 50:
            anomalies.append(
                {
                    "supplier": quotation.get("supplier") or "Unknown",
                    "total_cost": value,
                    "median_cost": median,
                    "deviation_percent": round(deviation, 1),
                    "direction": "high" if deviation > 0 else "low",
                }
            )

    return anomalies


def score_quotations(
    quotations: Sequence[Mapping[str, Any]],
    weights: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Score suppliers with normalized weights and currency-safe cost scoring."""
    normalized_weights = normalize_weights(weights)
    costs = [_num(quotation.get("total_cost")) for quotation in quotations]
    valid_costs = [cost for cost in costs if cost is not None]

    comparable_costs, cost_comparability_reason = _cost_comparability(quotations)
    if comparable_costs and valid_costs:
        min_cost, max_cost = min(valid_costs), max(valid_costs)
    else:
        min_cost = max_cost = None

    validation = validate_quotations(quotations)
    results: list[dict[str, Any]] = []

    # Pair validation records by position so duplicate supplier names stay distinct.
    for quotation, cost, validation_item in zip(quotations, costs, validation):
        supplier = quotation.get("supplier") or "Unknown"
        completeness = validation_item["completeness_score"]

        if min_cost is None or cost is None:
            cost_score = None
        elif max_cost == min_cost:
            cost_score = 100.0
        else:
            cost_score = 100 * (max_cost - cost) / (max_cost - min_cost)

        timeline = _timeline_score(quotation.get("delivery_timeline"))
        terms = _terms_score(quotation)

        risk_penalty = 0.0
        terms_text = str(quotation.get("terms_conditions") or "").lower()
        if "100% upfront" in terms_text or "full payment upfront" in terms_text:
            risk_penalty += 35
        if not quotation.get("warranty") and "warranty" not in terms_text:
            risk_penalty += 10

        risk_score = max(0.0, 100.0 - risk_penalty)
        components = {
            "cost": cost_score,
            "completeness": completeness,
            "timeline": timeline,
            "terms": terms,
            "risk": risk_score,
        }
        available = [
            (key, value)
            for key, value in components.items()
            if value is not None
        ]
        denominator = sum(normalized_weights[key] for key, _ in available) or 1.0
        score = (
            round(
                sum(normalized_weights[key] * value for key, value in available)
                / denominator,
                1,
            )
            if available
            else None
        )

        results.append(
            {
                "supplier": supplier,
                "score": score,
                "cost_score": (
                    round(cost_score, 1) if cost_score is not None else None
                ),
                "completeness_score": completeness,
                "timeline_score": (
                    round(timeline, 1) if timeline is not None else None
                ),
                "terms_score": round(terms, 1),
                "risk_score": round(risk_score, 1),
                "currency": quotation.get("currency"),
                "total_cost": cost,
                "missing_fields": validation_item["missing_fields"],
                "weights": normalized_weights,
                "cost_comparable": comparable_costs,
                "cost_comparability_reason": cost_comparability_reason,
            }
        )

    return sorted(
        results,
        key=lambda item: item["score"] if item["score"] is not None else -1,
        reverse=True,
    )
