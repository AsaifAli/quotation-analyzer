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
- **Portfolio session persistence:** a portfolio-backed gateway session can be reconstructed after a browser refresh while remaining governed by the existing gateway session lifetime.
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

When launched through the portfolio, QuoteSense uses a short-lived gateway session rather than embedding provider credentials in the frontend.

```text
Portfolio
   ↓
BYOK / session handoff
   ↓
Portfolio LLM Gateway
   ↓
QuoteSense
```

The page can reconstruct the existing portfolio session after a refresh; it does not extend the session lifetime.

## Local development

Use the repository's Docker Compose or documented API/UI startup path. The project also supports optional local inference through the existing configuration.

## Portfolio positioning

**Procurement decision intelligence** — explainable extraction, deterministic ranking, evidence traceability, and human-reviewed recommendations.
