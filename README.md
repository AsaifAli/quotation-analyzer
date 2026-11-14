# 📑 QuoteSense — Procurement Intelligence

> **AI-assisted quotation analysis that turns supplier documents into structured, comparable, explainable procurement decisions.**

Upload supplier quotations in **PDF, DOCX, TXT, or XLSX** and QuoteSense runs a controlled pipeline:

> **Ingest → Extract → Validate → Deterministically Score → Compare → Recommend → Review**

The system deliberately separates probabilistic LLM extraction/reasoning from deterministic business logic.

## What changed in the portfolio-ready release

- **Decision Cockpit:** results now open with a procurement-focused overview showing recommended supplier, score, confidence, source coverage, and risk review.
- **Scoring breakdown:** deterministic criteria and their contributions are presented explicitly rather than hiding the ranking logic behind an LLM response.
- **Why-this-supplier-won:** strongest scoring factors are surfaced as concise decision reasons.
- **Supplier comparison:** multi-quotation analysis is presented as a comparison workspace rather than a single oversized chart.
- **Risk review:** material commercial risks are elevated into the main decision view while detailed evidence remains available.
- **Results hierarchy:** overview and evidence come before raw/debug output.
- **Polished procurement workspace:** criteria chips, upload zone, readiness/status strip, sidebar workflow, and theme-aware UI were refined for a professional decision-cockpit experience.
- **One-time portfolio session handoff:** QuoteSense exchanges a short-lived launch code server-side and keeps the resulting bearer token in Streamlit session state, not in the browser URL.
- **Working hosted sidebar:** native Streamlit collapse/reopen behavior is repaired for hosted deployments.

## Core capabilities

- Multi-document quotation ingestion
- PDF / DOCX / TXT / XLSX processing
- LLM-based structured extraction
- Provider-independent LLM architecture
- Pydantic schema validation
- Deterministic multi-criteria scoring
- Completeness validation
- Risk detection
- Price anomaly detection
- Evidence traceability
- Prompt-injection-aware document handling
- FastAPI service
- Streamlit procurement workspace
- Docker Compose deployment
- Automated testing and CI

## Architecture

```text
Supplier Documents
        ↓
Document Processing
        ↓
LLM Extraction
        ↓
Normalization
        ↓
Pydantic Validation
        ↓
Deterministic Scoring
        ↓
Risk / Anomaly Detection
        ↓
Evidence-Grounded Reasoning
        ↓
Recommendation
        ↓
Human Review
```

### Core design principle

```text
LLM → Extract & Reason

Python → Validate & Score

Human → Make the Final Decision
```

## Gateway session model

When launched through the portfolio, QuoteSense receives a short-lived, single-use handoff code. It removes `portfolio_llm_handoff` from the browser URL before exchanging the code server-side. The resulting bearer token stays in Streamlit session state. The old `portfolio_llm_session` JWT query parameter is rejected.

```text
Portfolio BYOK session
        ↓
Single-use handoff code
        ↓
QuoteSense server-side exchange
        ↓
Shared Portfolio LLM Gateway
        ↓
Streamlit session token
```

Configure both variables in the QuoteSense hosting environment:

```text
LLM_GATEWAY_URL=https://<gateway-host>/v1
PORTFOLIO_SESSION_GATEWAY_URL=https://<gateway-host>
```

`LLM_GATEWAY_URL` is the OpenAI-compatible inference and session-status base and must end in `/v1`. `PORTFOLIO_SESSION_GATEWAY_URL` is the gateway root used for code exchange. Do not point the exchange URL at local LiteLLM. If Streamlit loses its browser session state, launch QuoteSense again from the portfolio to obtain a fresh code.

## Local development

Use the repository's Docker Compose or documented API/UI startup path. The project also supports optional local inference through the existing configuration.

## Portfolio positioning

**Procurement decision intelligence** — explainable extraction, deterministic ranking, evidence traceability, and human-reviewed recommendations.
