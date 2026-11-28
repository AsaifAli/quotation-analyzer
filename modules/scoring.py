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
        for key in ("terms_conditions", "validity_period", "payment_terms", "warranty", "support")
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
            for key in ("terms_conditions", "validity_period", "delivery_timeline", "payment_terms", "warranty", "support")
        ).lower()
        items: list[tuple[str, str]] = []

        if not quotation.get("warranty") and "warranty" not in text:
            items.append(("medium", "Warranty information is missing."))
        if "100% upfront" in text or "full payment upfront" in text:
            items.append(("high", "Full upfront payment is stated."))
        payment_text = str(quotation.get("payment_terms") or "").strip().lower()
        if not payment_text and "payment" not in text:
            items.append(("low", "Payment terms are not stated."))
        exclusions = quotation.get("exclusions") or []
        if isinstance(exclusions, str):
            exclusions = [exclusions]
        if exclusions:
            items.append((
                "medium",
                "The quotation lists exclusions; confirm that the omitted scope is acceptable.",
            ))
        if quotation.get("tax_amount") is None and quotation.get("tax_included") is None:
            items.append(("low", "Tax amount or tax-inclusion treatment is not stated."))
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
                    "currency": quotation.get("currency"),
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
        terms_text = " ".join(
            str(quotation.get(key) or "")
            for key in ("terms_conditions", "payment_terms", "warranty", "support")
        ).lower()
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
                "source_document": quotation.get("source_document"),
                "quote_reference": quotation.get("quote_reference"),
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





def _comparison_quote_labels(
    quotations: Sequence[Mapping[str, Any]],
) -> list[str]:
    """Create stable display labels so multiple bids from one supplier stay distinct."""
    supplier_counts: dict[str, int] = {}
    for quotation in quotations:
        supplier = str(quotation.get("supplier") or "Unknown").strip() or "Unknown"
        key = supplier.casefold()
        supplier_counts[key] = supplier_counts.get(key, 0) + 1

    labels: list[str] = []
    used: set[str] = set()
    for index, quotation in enumerate(quotations, start=1):
        supplier = str(quotation.get("supplier") or f"Quotation {index}").strip()
        if supplier_counts.get(supplier.casefold(), 0) > 1:
            detail = str(quotation.get("quote_reference") or "").strip()
            if not detail:
                source = str(quotation.get("source_document") or "").replace("\\", "/")
                detail = source.rsplit("/", 1)[-1].strip()
            detail = detail or f"Quote {index}"
            label = f"{supplier} — {detail}"
        else:
            label = supplier

        base = label
        suffix = 2
        while label.casefold() in used:
            label = f"{base} ({suffix})"
            suffix += 1
        labels.append(label)
        used.add(label.casefold())

    return labels


def build_comparison_matrix(
    quotations: Sequence[Mapping[str, Any]],
    scores: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a factual supplier matrix; never infer an unlisted item is excluded."""
    comparable, comparability_reason = _cost_comparability(quotations)
    priced = [
        (index, quotation, _num(quotation.get("total_cost")))
        for index, quotation in enumerate(quotations)
        if _num(quotation.get("total_cost")) is not None
    ]
    currencies = {
        str(quotation.get("currency") or "").strip().upper()
        for _, quotation, _ in priced
    }
    lowest = min(priced, key=lambda item: item[2]) if comparable and priced else None
    highest = max(priced, key=lambda item: item[2]) if comparable and priced else None

    quote_labels = _comparison_quote_labels(quotations)
    supplier_summaries = []

    def score_identity(item):
        return (
            str(item.get("supplier") or "").strip().casefold(),
            str(item.get("source_document") or "").strip().casefold(),
            str(item.get("quote_reference") or "").strip().casefold(),
            _num(item.get("total_cost")),
            str(item.get("currency") or "").strip().upper(),
        )

    score_by_quote = {
        score_identity(item): item
        for item in (scores or [])
    }
    for index, quotation in enumerate(quotations):
        amount = _num(quotation.get("total_cost"))
        supplier = str(quotation.get("supplier") or f"Quotation {index + 1}")
        score = score_by_quote.get(score_identity(quotation), {})
        delta = None
        delta_percent = None
        if comparable and amount is not None and lowest is not None:
            delta = round(amount - lowest[2], 2)
            delta_percent = round((amount - lowest[2]) / lowest[2] * 100, 2) if lowest[2] else 0.0
        supplier_summaries.append({
            "quote_label": quote_labels[index],
            "supplier": supplier,
            "quote_reference": quotation.get("quote_reference"),
            "source_document": quotation.get("source_document"),
            "total_cost": amount,
            "currency": quotation.get("currency"),
            "price_difference_from_lowest": delta,
            "percent_above_lowest": delta_percent,
            "score": score.get("score"),
            "delivery_timeline": quotation.get("delivery_timeline"),
            "payment_terms": quotation.get("payment_terms") or quotation.get("terms_conditions"),
            "warranty": quotation.get("warranty"),
            "support": quotation.get("support"),
            "validity_period": quotation.get("validity_period"),
            "tax_amount": _num(quotation.get("tax_amount")),
            "tax_included": quotation.get("tax_included"),
            "shipping_cost": _num(quotation.get("shipping_cost")),
            "discount_amount": _num(quotation.get("discount_amount")),
            "additional_charges": _num(quotation.get("additional_charges")),
            "exclusions": quotation.get("exclusions") or [],
            "line_item_count": len(quotation.get("line_items") or []),
        })

    # Item matching is deliberately conservative: only normalized exact
    # descriptions are aligned. Similar wording remains separate for review.
    grouped: dict[str, dict[str, Any]] = {}
    for index, quotation in enumerate(quotations):
        supplier = str(quotation.get("supplier") or f"Quotation {index + 1}")
        items = quotation.get("line_items") or []
        for item in items:
            if not isinstance(item, Mapping):
                continue
            description = str(item.get("description") or "").strip()
            key = re.sub(r"[^a-z0-9]+", " ", description.lower()).strip()
            if not key:
                continue
            group = grouped.setdefault(key, {
                "description": description,
                "offers": [],
                "not_listed_by": [],
            })
            group["offers"].append({
                "quote_label": quote_labels[index],
                "supplier": supplier,
                "quote_reference": quotation.get("quote_reference"),
                "quantity": _num(item.get("quantity")),
                "unit": item.get("unit"),
                "unit_price": _num(item.get("unit_price")),
                "total_price": _num(item.get("total_price")),
                "notes": item.get("notes"),
                "currency": quotation.get("currency"),
                "source_document": quotation.get("source_document"),
            })

    line_items = []
    all_quote_labels = quote_labels
    for group in grouped.values():
        offered = {offer["quote_label"] for offer in group["offers"]}
        group["not_listed_by"] = [
            quote_label for quote_label in all_quote_labels if quote_label not in offered
        ]
        priced_offers = [
            offer for offer in group["offers"]
            if offer.get("unit_price") is not None
        ]
        units = {
            str(offer.get("unit") or "").strip().lower()
            for offer in priced_offers
        }
        offer_currencies = {
            str(offer.get("currency") or "").strip().upper()
            for offer in priced_offers
        }
        unit_prices = [offer.get("unit_price") for offer in priced_offers]
        group["unit_price_comparable"] = (
            len(priced_offers) >= 2
            and all(offer.get("unit") and offer.get("currency") for offer in priced_offers)
            and len(units) == 1
            and len(offer_currencies) == 1
        )
        if group["unit_price_comparable"]:
            group["lowest_unit_price"] = min(unit_prices)
            group["highest_unit_price"] = max(unit_prices)
        else:
            group["lowest_unit_price"] = None
            group["highest_unit_price"] = None
        line_items.append(group)

    pricing_reconciliation = []
    for index, quotation in enumerate(quotations):
        subtotal = _num(quotation.get("subtotal"))
        total = _num(quotation.get("total_cost"))
        components = {
            "tax_amount": _num(quotation.get("tax_amount")),
            "shipping_cost": _num(quotation.get("shipping_cost")),
            "discount_amount": _num(quotation.get("discount_amount")),
            "additional_charges": _num(quotation.get("additional_charges")),
        }
        reported = [value for value in components.values() if value is not None]
        if subtotal is None or total is None or not reported:
            status = "insufficient_data"
            expected = None
            difference = None
        else:
            expected = subtotal + sum(
                value for key, value in components.items()
                if key != "discount_amount" and value is not None
            ) - (components["discount_amount"] or 0.0)
            difference = round(total - expected, 2)
            all_components_reported = all(value is not None for value in components.values())
            tolerance = max(1.0, abs(total) * 0.01)
            status = (
                "matched" if abs(difference) <= tolerance else "review"
            ) if all_components_reported else "partial_check"
        pricing_reconciliation.append({
            "quote_label": quote_labels[index],
            "supplier": quotation.get("supplier"),
            "quote_reference": quotation.get("quote_reference"),
            "source_document": quotation.get("source_document"),
            "currency": quotation.get("currency"),
            "subtotal": subtotal,
            **components,
            "stated_total": total,
            "calculated_total_from_reported_components": round(expected, 2) if expected is not None else None,
            "difference": difference,
            "status": status,
            "tax_included": quotation.get("tax_included"),
        })

    return {
        "cost_comparable": comparable,
        "cost_comparability_reason": comparability_reason,
        "currency": next(iter(currencies)) if len(currencies) == 1 else None,
        "lowest_price_supplier": lowest[1].get("supplier") if lowest else None,
        "lowest_price": lowest[2] if lowest else None,
        "highest_price": highest[2] if highest else None,
        "price_spread": round(highest[2] - lowest[2], 2) if lowest and highest else None,
        "suppliers": supplier_summaries,
        "line_items": line_items,
        "pricing_reconciliation": pricing_reconciliation,
    }
