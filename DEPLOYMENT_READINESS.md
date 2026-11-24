# Deployment Readiness

## Application topology

QuoteSense is a standalone Streamlit procurement workspace. Its Render Blueprint defines one Docker web service and uses the repository Dockerfile to launch the Streamlit interface. The app uses the existing analysis pipeline; its separate FastAPI API and local Compose topology remain available for local/integration use, not as an additional Render service in the current Blueprint.

## Hosted configuration

The Render manifest currently declares an OpenAI-compatible provider configuration using OpenRouter:

- `LLM_PROVIDER=openai`
- `OPENAI_BASE_URL=https://openrouter.ai/api/v1`
- `OPENAI_API_KEY` — set privately in Render
- `OPENAI_MODEL=openai/gpt-4o-mini`

It also declares the shared Engineering Assurance URL and a project-specific ingestion token. The harness token is optional for the core quotation-analysis workflow; telemetry delivery is best-effort and must never be a dependency for document processing.

The README also describes portfolio Gateway handoff. The hosted service configuration must be reconciled with the website's current project launch contract before claiming that website-launched BYOK is live. Do not add provider credentials to the browser or commit secrets.

## Live readiness

The configured Render hostname previously used for QuoteSense responded with a Render cold-start/wake-up page during a live check; a completed health response was not captured. That does not establish a failure, but it also does not establish that the application is ready.

Once the service is awake, verify:

1. `/_stcore/health` returns the Streamlit health response.
2. The workspace loads without import or provider configuration errors.
3. A synthetic PDF/DOCX quotation can be uploaded and analyzed end to end.
4. Deterministic score explanations, risk findings, supplier comparison, and exports render.
5. The model integration responds under the configured provider/session route.
6. The content-free telemetry event is accepted when its separate token is configured.

## Demo constraints

The free hosted application is a portfolio/demo service. Files are processed in temporary storage during a request and are not a durable audit repository. Use synthetic or approved sample quotations, not confidential supplier submissions. Persistent production procurement records, identity controls, retention, and operational recovery are not claimed.

## Local development

The repository's Docker Compose stack supports the API, Streamlit UI, local LiteLLM, PostgreSQL, and Redis. The local LiteLLM/Ollama services are not deployed by the single-service Render Blueprint.
