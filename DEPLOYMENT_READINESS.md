# Deployment Readiness

## Application topology

QuoteSense is a standalone Streamlit procurement workspace. Its Render Blueprint defines one Docker web service and uses the repository Dockerfile to launch the Streamlit interface. The app uses the existing analysis pipeline; its separate FastAPI API and local Compose topology remain available for local/integration use, not as an additional Render service in the current Blueprint.

**Verified hosted URL:** https://quotation-analyzer-9m4i.onrender.com

## Live verification — November 25, 2026

- `https://quotation-analyzer-9m4i.onrender.com/_stcore/health` returned `ok`.
- The landing route responded with the Streamlit application shell.
- The correct hostname is the one configured in the AI Engineering Studio project catalogue. Do not substitute the older guessed `quotation-analyzer.onrender.com` hostname.

The health response confirms that the Streamlit service is reachable. It does not prove a complete document-analysis, extraction, scoring, or export workflow. Those still require a synthetic end-to-end test.

## Hosted configuration

The Render manifest currently declares an OpenAI-compatible provider configuration using OpenRouter:

- `LLM_PROVIDER=openai`
- `OPENAI_BASE_URL=https://openrouter.ai/api/v1`
- `OPENAI_API_KEY` — set privately in Render
- `OPENAI_MODEL=openai/gpt-4o-mini`
- `EVALUATION_HARNESS_URL=https://ai-engineering-evaluation-harness.onrender.com`
- `EVALUATION_HARNESS_INGEST_TOKEN` — QuoteSense-specific ingestion token

The harness token is optional for the core quotation-analysis workflow; telemetry delivery is best-effort and must never be a dependency for document processing.

The README also describes portfolio Gateway handoff. The hosted service configuration must be reconciled with the website's current project launch contract before claiming that website-launched BYOK is live. Do not add provider credentials to the browser or commit secrets.

## Synthetic readiness checklist

1. Upload a synthetic PDF/DOCX quotation.
2. Confirm extraction and typed schema validation complete.
3. Verify deterministic score explanations, risk findings, and supplier comparison.
4. Review evidence traceability and confirm values can be traced back to source material.
5. Verify exports.
6. Test the model integration under the configured provider/session route.
7. Confirm a content-free telemetry event is accepted when its separate token is configured.

## Demo constraints

The free hosted application is a portfolio/demo service. Files are processed in temporary storage during a request and are not a durable audit repository. Use synthetic or approved sample quotations, not confidential supplier submissions. Persistent production procurement records, identity controls, retention, and operational recovery are not claimed.

## Local development

The repository Docker Compose stack supports the API, Streamlit UI, local LiteLLM, PostgreSQL, and Redis. The local LiteLLM/Ollama services are not deployed by the single-service Render Blueprint.