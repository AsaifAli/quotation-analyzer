"""Application orchestration: ingest -> extract -> validate -> score -> reason."""

import json
import logging
import time
from datetime import datetime, timezone

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import config
from harness_telemetry import record_event

from .document_processor import DocumentProcessor
from .llm_provider import LLMProvider
from .models import (
    ExtractionResult,
    AnalysisResult,
    RecommendationResult,
    normalize_extraction_payload,
    normalize_analysis_payload,
    normalize_recommendation_payload,
)
from .scoring import (
    validate_quotations,
    score_quotations,
    detect_risks,
    detect_price_anomalies,
    normalize_weights,
    build_comparison_matrix,
)
from .web_search import WebSearch


logger = logging.getLogger(__name__)


def _processing_event(trace, stage, status, message, metrics=None, callback=None):
    """Create a privacy-safe processing event and notify an optional observer."""
    safe_metrics = {}
    for key, value in (metrics or {}).items():
        if (
            isinstance(key, str)
            and key
            and len(key) <= 48
            and key.replace("_", "").isalnum()
            and isinstance(value, (bool, int, float))
        ):
            safe_metrics[key] = value

    event = {
        "sequence": len(trace) + 1,
        "stage": stage,
        "status": status,
        "message": message,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "metrics": safe_metrics,
    }
    trace.append(event)
    if callback:
        try:
            callback(event)
        except Exception:
            # Observability must never break procurement analysis.
            logger.debug("processing_stage_observer_failed", exc_info=True)
    return event


@dataclass
class AgentState:
    documents: List[str] = field(default_factory=list)
    quotations: List[Dict[str, Any]] = field(default_factory=list)
    validation: List[Dict[str, Any]] = field(default_factory=list)
    scores: List[Dict[str, Any]] = field(default_factory=list)
    analysis: Dict[str, Any] = field(default_factory=dict)
    recommendations: Dict[str, Any] = field(default_factory=dict)
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    risks: List[Dict[str, Any]] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)


class QuotationIntelligenceAgent:
    def __init__(
        self,
        provider: Optional[str] = None,
        gateway_token: str = "",
    ):
        self.llm = LLMProvider(
            provider,
            gateway_token=gateway_token,
        )
        self.processor = DocumentProcessor()
        self.web_search = WebSearch()
        self.state = AgentState()

    def _attach_evidence(
        self,
        quotation: Dict[str, Any],
        evidence: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        supplier = (quotation.get("supplier") or "").lower()
        references = []

        for item in evidence:
            text = item.get("text", "").lower()

            if supplier and supplier in text:
                references.append({
                    "source": item["source"],
                    "location": item["location"],
                    "excerpt": item.get("text", "")[:600],
                })

        quotation["evidence"] = references[:3] or [
            {
                "source": item["source"],
                "location": item["location"],
                "excerpt": item.get("text", "")[:600],
            }
            for item in evidence[:1]
        ]

        return quotation

    def extract_document(
        self,
        document_path: str,
    ) -> Dict[str, Any]:
        started = time.perf_counter()

        data = self.processor.extract(document_path)

        # The document is untrusted user content.
        # Trusted extraction instructions remain in the system prompt.
        extracted = self.llm.generate_json(
            data["text"],
            system=config.QUOTATION_EXTRACTION_PROMPT,
            schema=config.QUOTATION_SCHEMA,
        )

        normalized = normalize_extraction_payload(extracted)
        parsed = ExtractionResult.model_validate(normalized)

        quotations = [
            self._attach_evidence(
                {
                    **quotation.model_dump(),
                    "source_document": data["source"],
                },
                data["evidence"],
            )
            for quotation in parsed.quotations
        ]

        elapsed = round(time.perf_counter() - started, 3)

        return {
            "source": data["source"],
            "quotations": quotations,
            "evidence": data["evidence"],
            "truncated": data["truncated"],
            "characters": data["characters"],
            "elapsed_seconds": elapsed,
        }

    def extract(self, document_path):
        return self.process_documents(
            [document_path],
            analyze=False,
        )

    def process_documents(
        self,
        document_paths: List[str],
        query="Analyze quotations",
        criteria=None,
        weights=None,
        preferences=None,
        do_market=False,
        analyze=True,
        stage_callback=None,
        market_query=None,
    ):
        started = time.perf_counter()
        trace = []
        current_stage = ["processing"]

        def emit(stage, status, message, metrics=None):
            if status == "started":
                current_stage[0] = stage
            return _processing_event(
                trace,
                stage,
                status,
                message,
                metrics=metrics,
                callback=stage_callback,
            )

        try:
            result = self._process_documents(
                document_paths,
                query=query,
                criteria=criteria,
                weights=weights,
                preferences=preferences,
                do_market=do_market,
                analyze=analyze,
                stage_emitter=emit,
                market_query=market_query,
            )
            if result.get("status") == "success":
                result["processing_trace"] = trace
        except Exception:
            emit(
                current_stage[0],
                "failed",
                "This processing stage could not be completed.",
            )
            record_event(
                event_type="run.failed",
                status="failed",
                workflow="quotation_analysis",
                duration_ms=(time.perf_counter() - started) * 1000,
            )
            raise

        result_metrics = result.get("metrics") or {}
        completed = result.get("status") == "success"
        record_event(
            event_type="run.completed" if completed else "run.failed",
            status="success" if completed else "warning",
            workflow="quotation_analysis",
            duration_ms=(time.perf_counter() - started) * 1000,
            model=result.get("model") or result_metrics.get("llm_model"),
            metrics={
                "document_count": int(result_metrics.get("document_count") or 0),
                "quotation_count": int(result_metrics.get("quotation_count") or 0),
                "risk_count": len(result.get("risks") or []),
                "price_anomaly_count": len(result.get("price_anomalies") or []),
            },
        )
        return result

    def _process_documents(
        self,
        document_paths: List[str],
        query="Analyze quotations",
        criteria=None,
        weights=None,
        preferences=None,
        do_market=False,
        analyze=True,
        stage_emitter=None,
        market_query=None,
    ):
        if not document_paths:
            return {
                "status": "error",
                "message": "At least one document is required.",
            }

        started = time.perf_counter()
        documents = []
        all_quotations = []
        all_evidence = []

        for document_index, path in enumerate(document_paths, start=1):
            extract_started = time.perf_counter()
            if stage_emitter:
                stage_emitter(
                    "extract",
                    "started",
                    "Reading the document and extracting structured supplier information.",
                    {
                        "document_index": document_index,
                        "document_count": len(document_paths),
                    },
                )
            result = self.extract_document(path)
            documents.append(result)
            all_quotations.extend(result["quotations"])
            all_evidence.extend(result["evidence"])
            if stage_emitter:
                stage_emitter(
                    "extract",
                    "completed",
                    "Structured extraction completed for this document.",
                    {
                        "document_index": document_index,
                        "document_count": len(document_paths),
                        "quotation_count": len(result["quotations"]),
                        "evidence_item_count": len(result["evidence"]),
                        "extracted_field_count": sum(
                            len(item) for item in result["quotations"]
                        ),
                        "duration_ms": round(
                            (time.perf_counter() - extract_started) * 1000
                        ),
                    },
                )

        # Deduplicate exact supplier/cost pairs across duplicate uploads.
        seen = set()
        quotations = []

        for quotation in all_quotations:
            key = (
                str(quotation.get("supplier")).strip().lower(),
                quotation.get("total_cost"),
                str(quotation.get("currency")).upper(),
                str(quotation.get("quote_reference") or "").strip().lower(),
                str(quotation.get("source_document") or "").strip().lower(),
            )

            if key not in seen:
                seen.add(key)
                quotations.append(quotation)

        self.state.documents = [
            document["source"] for document in documents
        ]
        self.state.quotations = quotations
        self.state.evidence = all_evidence

        if stage_emitter:
            stage_emitter(
                "validation",
                "started",
                "Checking extracted records against the quotation schema.",
                {"quotation_count": len(quotations)},
            )
        self.state.validation = validate_quotations(quotations)
        if stage_emitter:
            stage_emitter(
                "validation",
                "completed",
                "Schema validation and completeness checks completed.",
                {
                    "quotation_count": len(quotations),
                    "missing_field_count": sum(
                        len(item.get("missing_fields") or [])
                        for item in self.state.validation
                    ),
                },
            )

        if stage_emitter:
            stage_emitter(
                "scoring",
                "started",
                "Calculating deterministic weighted supplier scores.",
                {"supplier_count": len(quotations)},
            )
        self.state.scores = score_quotations(quotations, weights)
        if stage_emitter:
            stage_emitter(
                "scoring",
                "completed",
                "Deterministic scoring completed using the configured business rules.",
                {
                    "supplier_count": len(quotations),
                    "scored_supplier_count": sum(
                        item.get("score") is not None for item in self.state.scores
                    ),
                },
            )

        if stage_emitter:
            stage_emitter(
                "risk_assessment",
                "started",
                "Checking missing commercial terms and eligible price anomalies.",
                {"supplier_count": len(quotations)},
            )
        self.state.risks = detect_risks(
            quotations,
            self.state.scores,
        )
        anomalies = detect_price_anomalies(quotations)
        if stage_emitter:
            stage_emitter(
                "risk_assessment",
                "completed",
                "Commercial risk and price-anomaly checks completed.",
                {
                    "risk_finding_count": sum(
                        len(item.get("items") or [])
                        for item in self.state.risks
                    ),
                    "price_anomaly_count": len(anomalies),
                },
            )

        result = {
            "status": "success",
            "documents": documents,
            "quotations": quotations,
            "validation": self.state.validation,
            "scores": self.state.scores,
            "comparison_matrix": build_comparison_matrix(
                quotations,
                self.state.scores,
            ),
            "risks": self.state.risks,
            "price_anomalies": anomalies,
            "weights": normalize_weights(weights),
            "evidence": all_evidence,
            "provider": self.llm.provider,
            "model": self.llm.model,
            "metrics": {
                "document_count": len(documents),
                "quotation_count": len(quotations),
                "pipeline_seconds": round(
                    time.perf_counter() - started,
                    3,
                ),
                "llm_provider": self.llm.provider,
                "llm_model": self.llm.model,
            },
        }

        lowered = query.lower()

        if (
            any(
                keyword in lowered
                for keyword in ["market", "benchmark", "industry"]
            )
            or do_market
        ):
            if stage_emitter:
                stage_emitter(
                    "market_research",
                    "started",
                    "Checking optional external market context. Source quotations remain the basis for supplier comparison.",
                )
            result["market"] = self.market_insights(scope=market_query)
            if stage_emitter:
                insight_data = result["market"].get("insights") or {}
                stage_emitter(
                    "market_research",
                    "completed",
                    "External context lookup completed; inspect source links and do not treat web snippets as verified supplier prices.",
                    {
                        "result_count": len(insight_data.get("results") or [])
                        if isinstance(insight_data, dict) else 0,
                        "available": isinstance(insight_data, dict)
                        and insight_data.get("status") == "success",
                    },
                )

        if analyze and (
            any(
                keyword in lowered
                for keyword in [
                    "recommend",
                    "best",
                    "choose",
                    "compare",
                    "analy",
                ]
            )
            or not any(
                keyword in lowered
                for keyword in ["validate", "extract"]
            )
        ):
            if stage_emitter:
                stage_emitter(
                    "analysis",
                    "started",
                    "Reviewing quotations, deterministic scores and flagged risks.",
                )
            result["analysis"] = self.analyze(criteria)
            if stage_emitter:
                stage_emitter(
                    "analysis",
                    "completed",
                    "Qualitative comparison completed.",
                )
            if stage_emitter:
                stage_emitter(
                    "recommendation",
                    "started",
                    "Preparing an evidence-informed recommendation for human review.",
                )
            result["recommendation"] = self.recommend(preferences)
            if stage_emitter:
                stage_emitter(
                    "recommendation",
                    "completed",
                    "Recommendation and alternatives are ready for review.",
                )

        if any(
            keyword in lowered
            for keyword in ["validate", "complete", "missing"]
        ):
            result["validation"] = {
                "status": "success",
                "validation": self.state.validation,
            }

        if stage_emitter:
            stage_emitter(
                "complete",
                "completed",
                "Quotation analysis completed. Review the evidence before making a decision.",
                {
                    "document_count": len(documents),
                    "quotation_count": len(quotations),
                    "scored_supplier_count": len(self.state.scores),
                    "risk_finding_count": sum(
                        len(item.get("items") or [])
                        for item in self.state.risks
                    ),
                    "price_anomaly_count": len(anomalies),
                },
            )

        return result

    def analyze(self, criteria=None):
        if not self.state.quotations:
            return {
                "status": "error",
                "message": "No quotations available.",
            }

        prompt = (
            config.COMPARISON_PROMPT
            + "\nCriteria: "
            + json.dumps(criteria or list(config.DEFAULT_WEIGHTS))
        )

        context = {
            "quotations": self.state.quotations,
            "scores": self.state.scores,
            "risks": self.state.risks,
        }

        result = self.llm.generate_json(
            json.dumps(context, indent=2),
            system=prompt,
            schema=config.ANALYSIS_SCHEMA,
        )

        result = AnalysisResult.model_validate(
            normalize_analysis_payload(result)
        ).model_dump()

        self.state.analysis = result

        return {
            "status": "success",
            "analysis": result,
            "scores": self.state.scores,
            "risks": self.state.risks,
        }

    def recommend(self, preferences=None):
        if not self.state.quotations:
            return {
                "status": "error",
                "message": "No quotations available.",
            }

        context = {
            "quotations": self.state.quotations,
            "scores": self.state.scores,
            "risks": self.state.risks,
            "preferences": preferences or {},
        }

        result = self.llm.generate_json(
            json.dumps(context, indent=2),
            system=config.RECOMMENDATION_PROMPT,
            schema=config.RECOMMENDATION_SCHEMA,
        )

        result = RecommendationResult.model_validate(
            normalize_recommendation_payload(result)
        ).model_dump()

        self.state.recommendations = result

        return {
            "status": "success",
            "recommendations": result,
            "scores": self.state.scores,
            "risks": self.state.risks,
        }

    def market_insights(self, location=None, scope=None):
        """Fetch optional external context without making it a dependency."""
        query = f"procurement pricing benchmark {scope or ''} {location or ''}".strip()
        try:
            insights = self.web_search.search(query)
        except Exception:
            logger.warning("market_context_lookup_failed", exc_info=True)
            insights = {
                "status": "unavailable",
                "message": "External market context could not be retrieved. The quotation comparison is still complete.",
                "results": [],
            }
        return {
            "status": "success",
            "query": query,
            "insights": insights,
        }

    def process(
        self,
        document_path,
        query="Analyze quotations",
        criteria=None,
        preferences=None,
    ):
        return self.process_documents(
            [document_path],
            query,
            criteria,
            preferences=preferences,
        )

    def reset(self):
        self.state = AgentState()