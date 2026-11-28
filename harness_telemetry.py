"""Best-effort, content-free telemetry to the studio evaluation service."""

from __future__ import annotations

import json
import logging
import math
import os
import uuid
from urllib.error import URLError
from urllib.request import Request, urlopen

LOGGER = logging.getLogger(__name__)


def record_event(
    *,
    event_type: str,
    status: str,
    workflow: str,
    duration_ms: float | None = None,
    model: str | None = None,
    metrics: dict | None = None,
    request_id: str | None = None,
    experiment_id: str | None = None,
    dataset_version: str | None = None,
    prompt_version: str | None = None,
    model_version: str | None = None,
    config_version: str | None = None,
) -> bool:
    """Send bounded event metadata. Missing config/network must never fail the app."""
    base_url = os.getenv("EVALUATION_HARNESS_URL", "").strip().rstrip("/")
    token = os.getenv("EVALUATION_HARNESS_INGEST_TOKEN", "").strip()
    if not base_url or not token:
        return False

    safe_metrics = {}
    for key, value in (metrics or {}).items():
        if (
            isinstance(key, str)
            and key
            and len(key) <= 48
            and all(ch.isalnum() or ch in "_@.-" for ch in key)
            and isinstance(value, (bool, int, float))
            and (not isinstance(value, float) or math.isfinite(value))
        ):
            safe_metrics[key] = value
        if len(safe_metrics) >= 24:
            break

    payload = {
        "event_id": uuid.uuid4().hex,
        "project": "quotesense",
        "event_type": event_type,
        "status": status,
        "workflow": str(workflow)[:80],
        "duration_ms": max(0, min(900000, float(duration_ms))) if duration_ms is not None else None,
        "model": str(model)[:120] if model else None,
        "request_id": str(request_id)[:100] if request_id else None,
        "metrics": safe_metrics,
    }
    for key, value in (
        ("experiment_id", experiment_id or os.getenv("EVALUATION_EXPERIMENT_ID")),
        ("dataset_version", dataset_version or os.getenv("EVALUATION_DATASET_VERSION")),
        ("prompt_version", prompt_version or os.getenv("EVALUATION_PROMPT_VERSION")),
        ("model_version", model_version),
        ("config_version", config_version or os.getenv("EVALUATION_CONFIG_VERSION")),
    ):
        if isinstance(value, str) and value.strip():
            payload[key] = value.strip()[:128]

    request = Request(
        f"{base_url}/api/application-events",
        data=json.dumps(payload, allow_nan=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=1.25) as response:
            return 200 <= int(response.status) < 300
    except (URLError, TimeoutError, OSError, ValueError):
        LOGGER.debug("Evaluation telemetry delivery failed; continuing without it.")
        return False
    except Exception:
        LOGGER.debug("Evaluation telemetry failed unexpectedly; continuing without it.")
        return False



def _finite_number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _bounded_count(value: object) -> int | None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        return None
    return min(value, 2_147_483_647)


def build_quote_evaluation_metrics(result: dict) -> dict[str, int | float]:
    """Project deterministic QuoteSense validation and procurement checks to scalars.

    No quotation, supplier, line-item, source-document, prompt or recommendation
    text is retained in the event. These are deterministic runtime checks, not
    an LLM-as-a-judge score.
    """
    if not isinstance(result, dict) or result.get("status") != "success":
        return {}

    metrics: dict[str, int | float] = {}
    pipeline_metrics = result.get("metrics") if isinstance(result.get("metrics"), dict) else {}
    document_count = _bounded_count(pipeline_metrics.get("document_count"))
    quote_count = _bounded_count(pipeline_metrics.get("quotation_count"))
    if document_count is not None:
        metrics["procurement.document_count"] = document_count
    if quote_count is not None:
        metrics["procurement.quote_count"] = quote_count

    validation = result.get("validation")
    if isinstance(validation, dict):
        validation_rows = validation.get("validation")
    else:
        validation_rows = validation
    if isinstance(validation_rows, list) and validation_rows:
        completeness = [
            float(item["completeness_score"])
            for item in validation_rows
            if isinstance(item, dict)
            and _finite_number(item.get("completeness_score"))
            and 0.0 <= float(item["completeness_score"]) <= 100.0
        ]
        if completeness:
            metrics["runtime.extraction_completeness"] = round(
                sum(completeness) / len(completeness) / 100.0, 6
            )
        valid_rows = [
            item for item in validation_rows
            if isinstance(item, dict) and isinstance(item.get("missing_fields"), list)
        ]
        if valid_rows:
            passed = sum(not item["missing_fields"] for item in valid_rows)
            metrics["runtime.quotation_validation_pass_rate"] = round(
                passed / len(valid_rows), 6
            )

    scores = result.get("scores")
    if isinstance(scores, list):
        scored = sum(
            isinstance(item, dict)
            and _finite_number(item.get("score"))
            and 0.0 <= float(item["score"]) <= 100.0
            for item in scores
        )
        denominator = quote_count if quote_count is not None else len(scores)
        if denominator > 0:
            metrics["runtime.scoring_coverage"] = round(
                min(scored, denominator) / denominator, 6
            )

    comparison = (
        result.get("comparison_matrix")
        if isinstance(result.get("comparison_matrix"), dict)
        else {}
    )
    if isinstance(comparison.get("cost_comparable"), bool):
        metrics["runtime.cost_comparability"] = float(comparison["cost_comparable"])

    line_items = comparison.get("line_items")
    if isinstance(line_items, list) and line_items:
        line_item_checks = [
            item for item in line_items
            if isinstance(item, dict) and isinstance(item.get("unit_price_comparable"), bool)
        ]
        if line_item_checks:
            comparable = sum(item["unit_price_comparable"] for item in line_item_checks)
            metrics["runtime.comparable_line_item_rate"] = round(
                comparable / len(line_item_checks), 6
            )

    reconciliation = comparison.get("pricing_reconciliation")
    if isinstance(reconciliation, list) and reconciliation:
        statuses = [
            str(item.get("status", "")).lower()
            for item in reconciliation
            if isinstance(item, dict)
        ]
        complete = [status for status in statuses if status in {"matched", "review"}]
        if statuses:
            metrics["runtime.price_reconciliation_coverage"] = round(
                len(complete) / len(statuses), 6
            )
        if complete:
            matched = sum(status == "matched" for status in complete)
            reviewed = sum(status == "review" for status in complete)
            metrics["runtime.price_reconciliation_match_rate"] = round(
                matched / len(complete), 6
            )
            metrics["runtime.price_reconciliation_review_rate"] = round(
                reviewed / len(complete), 6
            )

    risks = result.get("risks")
    if isinstance(risks, list):
        risk_finding_count = 0
        risked_quotation_count = 0
        for item in risks:
            if not isinstance(item, dict):
                continue
            findings = item.get("items")
            if isinstance(findings, list):
                count = len(findings)
            elif item.get("category") or item.get("level"):
                count = 1
            else:
                count = 0
            risk_finding_count += count
            risked_quotation_count += int(count > 0)
        metrics["runtime.risk_finding_count"] = min(risk_finding_count, 2_147_483_647)
        risk_denominator = quote_count if quote_count is not None else len(risks)
        if risk_denominator > 0:
            metrics["runtime.risked_quotation_rate"] = round(
                min(risked_quotation_count, risk_denominator) / risk_denominator, 6
            )

    anomalies = result.get("price_anomalies")
    if isinstance(anomalies, list):
        metrics["runtime.price_anomaly_count"] = min(len(anomalies), 2_147_483_647)

    analysis = result.get("analysis")
    if isinstance(analysis, dict) and analysis.get("status") is not None:
        metrics["runtime.analysis_available"] = float(analysis.get("status") == "success")

    recommendation = result.get("recommendation")
    if isinstance(recommendation, dict) and recommendation.get("status") is not None:
        primary = recommendation.get("primary_recommendation")
        metrics["runtime.recommendation_available"] = float(
            recommendation.get("status") == "success"
            and isinstance(primary, dict)
            and bool(primary.get("supplier"))
        )

    return metrics
