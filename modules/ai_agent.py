"""Application orchestration: ingest -> extract -> validate -> score -> reason."""

import json
import logging
import time

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import config

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
)
from .web_search import WebSearch


logger = logging.getLogger(__name__)


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
                quotation.model_dump(),
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

        for path in document_paths:
            result = self.extract_document(path)
            documents.append(result)
            all_quotations.extend(result["quotations"])
            all_evidence.extend(result["evidence"])

        # Deduplicate exact supplier/cost pairs across duplicate uploads.
        seen = set()
        quotations = []

        for quotation in all_quotations:
            key = (
                str(quotation.get("supplier")).strip().lower(),
                quotation.get("total_cost"),
                str(quotation.get("currency")).upper(),
            )

            if key not in seen:
                seen.add(key)
                quotations.append(quotation)

        self.state.documents = [
            document["source"] for document in documents
        ]
        self.state.quotations = quotations
        self.state.evidence = all_evidence
        self.state.validation = validate_quotations(quotations)
        self.state.scores = score_quotations(quotations, weights)
        self.state.risks = detect_risks(
            quotations,
            self.state.scores,
        )

        anomalies = detect_price_anomalies(quotations)

        result = {
            "status": "success",
            "documents": documents,
            "quotations": quotations,
            "validation": self.state.validation,
            "scores": self.state.scores,
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
            result["market"] = self.market_insights()

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
            result["analysis"] = self.analyze(criteria)
            result["recommendation"] = self.recommend(preferences)

        if any(
            keyword in lowered
            for keyword in ["validate", "complete", "missing"]
        ):
            result["validation"] = {
                "status": "success",
                "validation": self.state.validation,
            }

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

    def market_insights(self, location=None):
        query = f"procurement quotation pricing benchmark {location or ''}".strip()

        return {
            "status": "success",
            "query": query,
            "insights": self.web_search.search(query),
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