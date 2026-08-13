"""FastAPI service for the quotation intelligence engine."""
import os, tempfile, json
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from modules.ai_agent import QuotationIntelligenceAgent
import config

app=FastAPI(title="Quotation Intelligence API",version="3.2.0",description="AI-assisted procurement quotation analysis with deterministic validation and scoring.")
app.add_middleware(CORSMiddleware,allow_origins=[x.strip() for x in os.getenv("CORS_ORIGINS","http://localhost:8501").split(",") if x.strip()],allow_methods=["GET","POST"],allow_headers=["*"])

@app.get("/health")
def health(): return {"status":"ok","provider":config.LLM_PROVIDER}

@app.get("/health/llm")
def llm_health():
    try:
        from modules.llm_provider import LLMProvider
        return LLMProvider().health()
    except Exception as exc: return {"available":False,"error":str(exc)}

@app.get("/ready")
def ready():
    info=llm_health()
    if not info.get("available"): raise HTTPException(503,"LLM provider is not ready")
    return {"status":"ready","llm":info}

@app.post("/api/v1/analyses")
async def analyze(files:list[UploadFile]=File(...),query:str=Form("Analyze quotations"),criteria:str=Form("")):
    if not files: raise HTTPException(400,"At least one quotation file is required.")
    paths=[]; names=[]
    try:
        for file in files:
            ext=os.path.splitext(file.filename or "")[1].lower()
            if ext not in config.SUPPORTED_FORMATS: raise HTTPException(400,f"Unsupported file type: {ext}")
            data=await file.read()
            if len(data)>config.MAX_FILE_SIZE_MB*1024*1024: raise HTTPException(413,f"{file.filename} exceeds {config.MAX_FILE_SIZE_MB} MB.")
            fd,path=tempfile.mkstemp(suffix=ext)
            with os.fdopen(fd,"wb") as out: out.write(data)
            paths.append(path); names.append(file.filename)
        criteria_list=[x.strip() for x in criteria.split(",") if x.strip()] or config.DEFAULT_CRITERIA
        result=QuotationIntelligenceAgent().process_documents(paths,query=query,criteria=criteria_list)
        result["uploaded_files"]=names
        return result
    except HTTPException: raise
    except Exception as exc: raise HTTPException(500,str(exc))
    finally:
        for path in paths:
            if os.path.exists(path): os.unlink(path)

@app.post("/analyze")
async def legacy_analyze(file:UploadFile=File(...),query:str=Form("Analyze quotations"),criteria:str=Form("")):
    return await analyze([file],query,criteria)

@app.get("/")
def root(): return {"service":"quotation-intelligence-api","version":"3.2.0","docs":"/docs","health":"/health"}
