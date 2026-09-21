"""Safe smoke contract for the Agent Harness.

Exercises QuoteSense's real document-processing and deterministic validation /
scoring code on the repository's own sample quotation fixture. It deliberately
does not call the LLM on every fleet-health run.
"""
from __future__ import annotations

import re
from pathlib import Path

from fastapi import FastAPI

from modules.document_processor import DocumentProcessor
from modules.scoring import detect_price_anomalies, detect_risks, score_quotations, validate_quotations

app = FastAPI(title="QuoteSense Harness Adapter", version="1.0.0")
SAMPLE = Path(__file__).resolve().parent / "sample_data" / "sample_quotations.txt"


@app.get("/health")
def health():
    return {"status": "ok", "service": "quotesense-harness"}


@app.post("/harness/smoke")
def smoke(payload: dict | None = None):
    extracted = DocumentProcessor().extract(str(SAMPLE))
    text = extracted.get("text", "")
    suppliers = re.findall(r"Supplier:\s*(.+)", text)
    costs = re.findall(r"Cost:\s*USD\s*([0-9,]+(?:\.\d+)?)", text)
    deliveries = re.findall(r"Delivery:\s*([0-9]+)\s*weeks", text)

    quotations = [
        {
            "supplier": supplier.strip(),
            "total_cost": float(cost.replace(",", "")),
            "currency": "USD",
            "delivery_weeks": int(delivery),
        }
        for supplier, cost, delivery in zip(suppliers, costs, deliveries)
    ]

    validation = validate_quotations(quotations)
    scores = score_quotations(quotations)
    risks = detect_risks(quotations, scores)
    anomalies = detect_price_anomalies(quotations)

    checks = {
        "document_processing": bool(text.strip()),
        "sample_fixture_read": SAMPLE.exists(),
        "quotation_count": len(quotations),
        "schema_validation": all(item.get("valid", True) for item in validation),
        "deterministic_scoring": len(scores) == len(quotations) and bool(scores),
        "risk_analysis": isinstance(risks, list),
        "price_anomaly_analysis": isinstance(anomalies, list),
    }
    core_pass = all(checks[key] for key in (
        "document_processing",
        "sample_fixture_read",
        "schema_validation",
        "deterministic_scoring",
        "risk_analysis",
        "price_anomaly_analysis",
    ))

    return {
        "status": "completed" if core_pass else "failed",
        "service": "quotesense",
        "workflow": "harness_smoke",
        "checks": checks,
        "derived": {
            "suppliers": [q["supplier"] for q in quotations],
            "lowest_cost": min((q["total_cost"] for q in quotations), default=None),
        },
        "payload_received": bool(payload),
    }
