# 📑 Quotation Intelligence Platform

**Portfolio-grade AI engineering project for procurement quotation analysis.**

Upload supplier quotations in **PDF, DOCX, TXT or XLSX** and the system runs a controlled pipeline:

> **Ingest → Extract → Validate → Deterministically Score → Compare → Recommend → Show Evidence**

The project deliberately does **not** make the LLM the sole decision-maker. Numeric scoring and completeness checks are deterministic; the LLM is used for document extraction and cautious reasoning over the resulting evidence.

## Portfolio highlights

- 🧠 **LLM provider abstraction:** provider abstraction with cloud-first `auto` mode and optional Ollama for local/private inference.
- 📋 **Structured extraction:** quotation fields are normalized into JSON.
- 🧮 **Deterministic scoring:** cost and completeness are calculated in Python, reducing LLM-driven ranking errors.
- 🔎 **Evidence traceability:** source snippets/pages/sheets are retained alongside extraction results.
- ⚠️ **Completeness validation:** missing fields are explicitly surfaced before a recommendation.
- 📊 **Streamlit dashboard:** overview, quotation table, scoring, validation, recommendation, evidence and raw output.
- 🚀 **FastAPI service:** production-shaped `/health`, `/health/llm`, `/analyze` endpoints and Swagger docs.
- 🐳 **Docker Compose:** lightweight API + Streamlit base stack; Ollama is an explicit optional overlay with persistent model storage.
- 🧪 **Automated tests:** core ingestion, scoring, JSON parsing and API health tests.
- 🔐 **Secret-safe configuration:** `.env` is ignored and credentials are environment-driven.
- 🌐 **Optional external research:** Tavily is disabled unless explicitly configured; no mock market data is generated.
- 🎯 **Deployment-friendly:** all core services are containerized; Ollama can use CPU or an optional NVIDIA GPU override.

## Architecture

### Local development

```text
Browser
  │
  ▼
Streamlit
  │
  ▼
Quotation pipeline
  │
  ├── deterministic validation/scoring
  └── LLM provider abstraction
          ├── LiteLLM
          └── optional Ollama
```

### Public demo

```text
Browser
  │
  ▼
Streamlit on Render
  │
  ▼
Quotation pipeline
  │
  └── OpenAI-compatible HTTPS LLM endpoint
```

The FastAPI service remains part of the repository for API demos and local development, while the first Render deployment uses Streamlit directly to keep the public demo lightweight.


## Why the architecture is stronger

### 1. LLM + deterministic hybrid

A common portfolio weakness is asking an LLM to extract data and then blindly choose the cheapest or "best" result. This project separates those responsibilities:

- **LLM:** extraction and qualitative reasoning.
- **Python:** completeness checks and measurable cost scoring.
- **Human:** final procurement decision.

The UI explicitly labels the score so an interviewer can see how it was calculated.

### 2. Traceability

PDF pages, DOCX paragraphs, text documents and XLSX sheets are represented as evidence blocks. The UI exposes these snippets so extracted fields can be investigated rather than treated as unexplained AI output.

### 3. Production-shaped services

The repository includes both a browser-facing Streamlit application and a FastAPI backend. The API provides health checks and automatic OpenAPI/Swagger documentation.

### 4. Container orchestration

`docker-compose.yml` starts:

1. **Ollama** — local model runtime.
2. **ollama-init** — pulls the configured model once.
3. **API** — FastAPI backend.
4. **Streamlit** — user interface.

The Ollama model is persisted in a named Docker volume, so it is not downloaded on every restart.

## Quick start — Docker Compose

The base stack intentionally does **not** start Ollama. This keeps cloud deployment lightweight and avoids downloading a local model when a hosted LLM is configured.

```bash
cp .env.example .env
# Set GEMINI_API_KEY or OPENAI_API_KEY, then:
docker compose up --build
```

Open:

- Streamlit: `http://localhost:8501`
- API: `http://localhost:8000`
- Swagger: `http://localhost:8000/docs`

### Local Ollama mode

If you want fully local/private inference:

```bash
docker compose -f docker-compose.yml -f docker-compose.ollama.yml up --build
```

The Ollama model is persisted in a named volume. The first startup downloads the configured model.

### NVIDIA GPU

With Docker + NVIDIA Container Toolkit:

```bash
docker compose -f docker-compose.yml -f docker-compose.ollama.yml -f docker-compose.gpu.yml up --build
```

Ollama is optional rather than a hard dependency of the application.

## Local development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

For a local Ollama installation, change:

```env
OLLAMA_BASE_URL=http://localhost:11434
```

Then:

```bash
ollama pull qwen3:1.7b
streamlit run streamlit_app.py
```

API:

```bash
uvicorn app:app --reload --port 8000
```

## Test

```bash
pytest -q
```

Tests intentionally include an offline path so CI does not require an LLM API key.

## CLI

```bash
python agent_interface.py \
  --document sample_data/sample_quotations.txt \
  --query "Compare quotations and recommend the strongest option"
```

## API example

```bash
curl -X POST http://localhost:8000/analyze \
  -F "file=@sample_data/sample_quotations.txt" \
  -F "query=Compare the quotations and identify risks" \
  -F "criteria=cost,completeness,timeline,terms"
```

## Project structure

```text
.
├── app.py                       # FastAPI service
├── streamlit_app.py             # Streamlit UI
├── launcher.py                  # Local launcher
├── agent_interface.py           # CLI
├── config.py                    # Environment configuration/prompts
├── modules/
│   ├── ai_agent.py              # Orchestration
│   ├── document_processor.py    # Multi-format ingestion + evidence
│   ├── llm_provider.py          # Ollama/OpenAI/Gemini abstraction
│   ├── scoring.py               # Deterministic scoring/validation
│   └── web_search.py             # Optional Tavily integration
├── tests/
│   ├── test_core.py
│   └── test_api.py
├── sample_data/
│   └── sample_quotations.txt
├── Dockerfile
├── docker-compose.yml
├── docker-compose.gpu.yml
├── .github/workflows/ci.yml
└── requirements.txt
```

## Known limitations / honest engineering notes

- Scanned PDFs are not OCR'd yet; image-only PDFs need OCR before extraction.
- Evidence blocks currently provide source locations/snippets, but not field-level bounding boxes.
- Qualitative criteria such as quality/reputation are not fabricated into numeric scores.
- Shared public deployment should add authentication, rate limiting and persistent audit storage.
- Procurement recommendations should be reviewed by a human before contractual decisions.

## 🚀 Deployment

**Status:** Deployed

The application is deployed as a public portfolio demonstration.

**Architecture:** GitHub Actions → Docker → Cloud deployment

> Live demo access is provided selectively for evaluation/interviews.

## Disclaimer

This is a portfolio/decision-support system. It is not financial, legal, tax or procurement advice.


## Robust extraction normalization

The extraction layer is deliberately tolerant of provider/model differences. Before domain validation it normalizes common JSON shapes (wrapped objects, bare arrays and single records), nested scalar objects, and localized monetary strings into a canonical Pydantic model. This prevents provider-specific formatting from leaking into business logic and avoids supplier/document-specific hardcoding.

### Results behavior

Completed analysis results are stored independently of the current file uploader selection. Removing all files from the uploader does not erase the last completed analysis. The dashboard labels those results as the last completed analysis and provides an explicit **Clear previous results** action. If a different set of files is selected, the previous results remain visible but are clearly marked as not yet analyzed until the user runs a new analysis.
