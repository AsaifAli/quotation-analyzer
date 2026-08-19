"""Application orchestration: ingest -> structured extraction -> validation -> scoring -> reasoning."""
import json, logging, time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import config
from .document_processor import DocumentProcessor
from .llm_provider import LLMProvider
from .models import ExtractionResult, Quotation, AnalysisResult, RecommendationResult, normalize_extraction_payload, normalize_analysis_payload, normalize_recommendation_payload
from .scoring import validate_quotations, score_quotations, detect_risks, detect_price_anomalies, normalize_weights
from .web_search import WebSearch
logger=logging.getLogger(__name__)

@dataclass
class AgentState:
    documents: List[str]=field(default_factory=list); quotations: List[Dict[str,Any]]=field(default_factory=list)
    validation: List[Dict[str,Any]]=field(default_factory=list); scores: List[Dict[str,Any]]=field(default_factory=list)
    analysis: Dict[str,Any]=field(default_factory=dict); recommendations: Dict[str,Any]=field(default_factory=dict)
    evidence: List[Dict[str,Any]]=field(default_factory=list); risks: List[Dict[str,Any]]=field(default_factory=list)
    metrics: Dict[str,Any]=field(default_factory=dict)

class QuotationIntelligenceAgent:
    def __init__(self,provider:Optional[str]=None,gateway_token: str = ""): self.llm=LLMProvider(provider, gateway_token=gateway_token); self.processor=DocumentProcessor(); self.web_search=WebSearch(); self.state=AgentState()
    def _attach_evidence(self,q:Dict[str,Any], evidence:List[Dict[str,Any]]) -> Dict[str,Any]:
        supplier=(q.get("supplier") or "").lower(); refs=[]
        for item in evidence:
            text=item.get("text","").lower()
            if supplier and supplier in text: refs.append({"source":item["source"],"location":item["location"],"excerpt":item.get("text","")[:600]})
        q["evidence"]=refs[:3] or [{"source":x["source"],"location":x["location"],"excerpt":x.get("text","")[:600]} for x in evidence[:1]]
        return q
    def extract_document(self,document_path:str)->Dict[str,Any]:
        started=time.perf_counter(); data=self.processor.extract(document_path)
        extracted=self.llm.generate_json(config.QUOTATION_EXTRACTION_PROMPT,data["text"],schema=config.QUOTATION_SCHEMA)
        # LLMs occasionally return a bare array, a single record, or loosely typed
        # money/supplier objects. Normalize those shapes before Pydantic validation.
        normalized=normalize_extraction_payload(extracted)
        parsed=ExtractionResult.model_validate(normalized)
        quotes=[]
        for q in parsed.quotations: quotes.append(self._attach_evidence(q.model_dump(),data["evidence"]))
        elapsed=round(time.perf_counter()-started,3)
        return {"source":data["source"],"quotations":quotes,"evidence":data["evidence"],"truncated":data["truncated"],"characters":data["characters"],"elapsed_seconds":elapsed}
    def extract(self,document_path): return self.process_documents([document_path], analyze=False)
    def process_documents(self,document_paths:List[str],query="Analyze quotations",criteria=None,weights=None,preferences=None,do_market=False):
        if not document_paths: return {"status":"error","message":"At least one document is required."}
        started=time.perf_counter(); docs=[]; all_quotes=[]; all_evidence=[]
        for path in document_paths:
            result=self.extract_document(path); docs.append(result); all_quotes.extend(result["quotations"]); all_evidence.extend(result["evidence"])
        # Deduplicate exact supplier/cost pairs across duplicate uploads.
        seen=set(); quotations=[]
        for q in all_quotes:
            key=(str(q.get("supplier")).strip().lower(),q.get("total_cost"),str(q.get("currency")).upper())
            if key not in seen: seen.add(key); quotations.append(q)
        self.state.documents=[d["source"] for d in docs]; self.state.quotations=quotations; self.state.evidence=all_evidence
        self.state.validation=validate_quotations(quotations); self.state.scores=score_quotations(quotations,weights); self.state.risks=detect_risks(quotations,self.state.scores)
        anomalies=detect_price_anomalies(quotations)
        result={"status":"success","documents":docs,"quotations":quotations,"validation":self.state.validation,"scores":self.state.scores,"risks":self.state.risks, "price_anomalies": anomalies,
                "weights":normalize_weights(weights),"evidence":all_evidence,"provider":self.llm.provider,"model":self.llm.model,
                "metrics":{"document_count":len(docs),"quotation_count":len(quotations),"pipeline_seconds":round(time.perf_counter()-started,3),"llm_provider":self.llm.provider,"llm_model":self.llm.model}}
        lowered=query.lower()
        if any(k in lowered for k in ["market","benchmark","industry"]) or do_market: result["market"]=self.market_insights()
        if any(k in lowered for k in ["recommend","best","choose","compare","analy"] ) or not any(k in lowered for k in ["validate","extract"]):
            result["analysis"]=self.analyze(criteria); result["recommendation"]=self.recommend(preferences)
        if any(k in lowered for k in ["validate","complete","missing"]): result["validation"]={"status":"success","validation":self.state.validation}
        return result
    def analyze(self,criteria=None):
        if not self.state.quotations: return {"status":"error","message":"No quotations available."}
        prompt=config.COMPARISON_PROMPT+"\nCriteria: "+json.dumps(criteria or list(config.DEFAULT_WEIGHTS))
        context={"quotations":self.state.quotations,"scores":self.state.scores,"risks":self.state.risks}
        result=self.llm.generate_json(prompt,json.dumps(context,indent=2),schema=config.ANALYSIS_SCHEMA); result=AnalysisResult.model_validate(normalize_analysis_payload(result)).model_dump(); self.state.analysis=result
        return {"status":"success","analysis":result,"scores":self.state.scores,"risks":self.state.risks}
    def recommend(self,preferences=None):
        if not self.state.quotations: return {"status":"error","message":"No quotations available."}
        context={"quotations":self.state.quotations,"scores":self.state.scores,"risks":self.state.risks,"preferences":preferences or {}}
        result=self.llm.generate_json(config.RECOMMENDATION_PROMPT,json.dumps(context,indent=2),schema=config.RECOMMENDATION_SCHEMA); result=RecommendationResult.model_validate(normalize_recommendation_payload(result)).model_dump(); self.state.recommendations=result
        return {"status":"success","recommendations":result,"scores":self.state.scores,"risks":self.state.risks}
    def market_insights(self,location=None):
        query=f"procurement quotation pricing benchmark {location or ''}".strip(); return {"status":"success","query":query,"insights":self.web_search.search(query)}
    def process(self,document_path,query="Analyze quotations",criteria=None,preferences=None): return self.process_documents([document_path],query,criteria,preferences=preferences)
    def reset(self): self.state=AgentState()
