# Render Deployment

## Public demo topology

The Render demo intentionally runs the Streamlit application as a single web service:

Streamlit -> OpenAI-compatible HTTPS endpoint -> LLM

The local LiteLLM/Ollama Compose files remain for development and private/local inference. They are not required for the public Render demo.

## Required Render secret

Set `OPENAI_API_KEY` in Render. The example `render.yaml` uses OpenRouter's OpenAI-compatible API endpoint, but any compatible endpoint can be used by changing `OPENAI_BASE_URL` and `OPENAI_MODEL`.

## Render settings

- Runtime: Docker
- Region: Singapore
- Health check: `/_stcore/health`
- Start command: provided by the Dockerfile
- Persistent disk: not required for the demo

## Important demo constraint

The Free deployment is a portfolio/demo service, not a production procurement system. Files are processed in temporary storage during a request and are not intended to become a durable audit repository.
