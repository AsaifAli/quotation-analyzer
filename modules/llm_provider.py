"""Provider abstraction with a common structured-output contract.

The application asks every provider for JSON conforming to the same schema.
Provider-specific response-format details are isolated here so changing models
or vendors does not change downstream application code.
"""
import json
import logging
import re
import time
from typing import Any, Dict, Optional

import requests

import config
from llm_gateway_context import get_llm_gateway_token

logger = logging.getLogger(__name__)


def extract_json(text: Any) -> Any:
    """Parse JSON from provider output without assuming a particular shape."""
    if isinstance(text, (dict, list)):
        return text
    if not text:
        return None

    cleaned = str(text).strip()
    cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.S | re.I).strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\s*```$", "", cleaned).strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Recover the first complete-looking JSON object/array when a model adds
    # harmless prose around an otherwise valid response.
    decoder = json.JSONDecoder()
    for index, char in enumerate(cleaned):
        if char not in "[{":
            continue
        try:
            value, _ = decoder.raw_decode(cleaned[index:])
            if isinstance(value, (dict, list)):
                return value
        except json.JSONDecodeError:
            continue
    return None


def _gemini_compatible_schema(schema: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Convert our provider-neutral JSON Schema into Gemini's supported subset.

    Gemini structured output supports a deliberately smaller JSON Schema subset.
    In particular, provider-neutral union types such as ["string", "object", "null"]
    are not a safe wire format across models.  We normalize these schemas at the
    provider boundary instead of weakening the domain models or adding quotation-
    specific exceptions.
    """
    if not schema:
        return None

    def convert(node: Any, parent_key: str = "") -> Any:
        if isinstance(node, list):
            return [convert(item, parent_key) for item in node]
        if not isinstance(node, dict):
            return node

        out = {}
        raw_type = node.get("type")
        if isinstance(raw_type, list):
            non_null = [t for t in raw_type if t != "null"]
            # Gemini's structured-output subset is safest with one concrete type.
            # Prefer object for supplier-like structured values, otherwise string.
            if "object" in non_null:
                out["type"] = "object"
            elif "array" in non_null:
                out["type"] = "array"
            elif "number" in non_null:
                out["type"] = "number"
            elif "integer" in non_null:
                out["type"] = "integer"
            elif "boolean" in non_null:
                out["type"] = "boolean"
            else:
                out["type"] = "string"
        elif raw_type:
            out["type"] = raw_type

        # Only forward fields supported by Gemini's responseSchema subset.
        # Numeric minimum/maximum and JSON Schema extras are intentionally not
        # sent because Gemini's schema is not full JSON Schema.
        for key in ("title", "description", "enum", "format", "minItems", "maxItems"):
            if key in node:
                out[key] = node[key]

        if "properties" in node and isinstance(node["properties"], dict):
            out["properties"] = {k: convert(v, k) for k, v in node["properties"].items()}
        if "required" in node:
            out["required"] = list(node["required"])
        if "items" in node:
            out["items"] = convert(node["items"], parent_key)
        # Gemini's REST responseSchema does not accept JSON Schema's
        # additionalProperties keyword. Keep it in the provider-neutral/domain
        # schema for OpenAI/Ollama, but deliberately omit it at the Gemini wire
        # boundary. This also handles schemas containing additionalProperties
        # inside array item objects.
        if "propertyOrdering" in node:
            out["propertyOrdering"] = node["propertyOrdering"]
        return out

    return convert(schema)


class LLMProvider:
    """Expose one provider-independent generate/generate_json interface."""

    def __init__(self, provider: Optional[str] = None, gateway_token: str = ""):
        self._active_gemini_model = None

        # Resolve the gateway session BEFORE touching local provider config.
        # A BYOK gateway session is provider-agnostic (the gateway resolves the
        # real upstream provider/model server-side and always speaks the
        # OpenAI-compatible wire format), so its presence must short-circuit
        # local provider resolution entirely. Previously local provider
        # resolution ran first and could raise (LLM_PROVIDER=auto with no
        # local cloud key configured) or silently win the dispatch in
        # generate() (LLM_PROVIDER=gemini/ollama), both of which caused a
        # valid gateway token to never be used.
        self.gateway_token = (gateway_token or "").strip() or get_llm_gateway_token()
        self.gateway_url = config.LLM_GATEWAY_URL.strip()
        self.use_gateway = bool(self.gateway_token and self.gateway_url)

        if self.use_gateway:
            # The gateway always exposes an OpenAI-compatible endpoint; the
            # actual upstream provider/model is chosen server-side by the
            # gateway session, not by local config.
            self.provider = "openai"
            return

        requested = (provider or config.LLM_PROVIDER).lower()
        self.provider = self._resolve_provider(requested)
        if self.provider not in {"ollama", "openai", "litellm", "gemini"}:
            raise ValueError("LLM_PROVIDER must be auto, ollama, openai, litellm, or gemini")

    def _resolve_provider(self, requested: str) -> str:
        if requested != "auto":
            return requested
        if config.GEMINI_API_KEY:
            return "gemini"
        if config.OPENAI_API_KEY:
            return "openai"
        if config.OLLAMA_ENABLED:
            return "ollama"
        raise RuntimeError(
            "LLM_PROVIDER=auto but no cloud API key is configured and Ollama is disabled. "
            "Set GEMINI_API_KEY, OPENAI_API_KEY, or explicitly enable Ollama."
        )

    @property
    def model(self) -> str:
        if self.use_gateway:
            # The gateway session (not local config) owns the real model;
            # session status metadata is what displays the true value.
            return "gateway-session"
        if self.provider == "gemini":
            return self._active_gemini_model or config.GEMINI_MODEL
        return {"ollama": config.OLLAMA_MODEL, "openai": config.OPENAI_MODEL, "litellm": config.LITELLM_MODEL}[self.provider]

    def generate(self, prompt: str, system: str = "", temperature: float = 0.1,
                 schema: Optional[Dict[str, Any]] = None) -> str:
        last = None
        for attempt in range(config.LLM_MAX_RETRIES + 1):
            try:
                if self.use_gateway:
                    return self._openai(prompt, system, temperature, schema)
                if self.provider == "ollama":
                    return self._ollama(prompt, system, temperature, schema)
                if self.provider in {"openai", "litellm"}:
                    return self._openai(prompt, system, temperature, schema)
                return self._gemini(prompt, system, temperature, schema)
            except requests.HTTPError as exc:
                last = exc
                status = getattr(exc.response, "status_code", None)
                if status is not None and 400 <= status < 500:
                    raise RuntimeError(f"{self.provider} request failed ({status}): {exc}") from exc
                if attempt < config.LLM_MAX_RETRIES:
                    time.sleep(1.0 * (attempt + 1))
            except (requests.RequestException, RuntimeError) as exc:
                last = exc
                if attempt < config.LLM_MAX_RETRIES:
                    time.sleep(1.0 * (attempt + 1))
        raise RuntimeError(f"{self.provider} request failed after retries: {last}")

    def generate_json(self, prompt: str, system: str = "", schema: Optional[Dict[str, Any]] = None) -> Any:
        parsed = extract_json(self.generate(prompt, system, 0.0, schema))
        if parsed is None:
            raise ValueError("LLM returned invalid JSON.")
        return parsed

    def _ollama(self, prompt: str, system: str, temperature: float, schema: Optional[Dict[str, Any]]) -> str:
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "stream": False,
            "format": schema or "json",
            "keep_alive": config.OLLAMA_KEEP_ALIVE,
            "think": config.OLLAMA_THINK,
            "options": {
                "temperature": temperature,
                "num_ctx": config.OLLAMA_NUM_CTX,
                "num_predict": config.OLLAMA_NUM_PREDICT,
            },
        }
        r = requests.post(f"{config.OLLAMA_BASE_URL.rstrip('/')}/api/chat", json=payload, timeout=config.REQUEST_TIMEOUT)
        r.raise_for_status()
        return r.json().get("message", {}).get("content", "")

    def _openai(self, prompt: str, system: str, temperature: float,
                schema: Optional[Dict[str, Any]]) -> str:
        gateway_token = self.gateway_token or get_llm_gateway_token()
        gateway_url = config.LLM_GATEWAY_URL.strip()
        if gateway_token and gateway_url:
            api_key = gateway_token
            base_url = gateway_url
            effective_model = None  # gateway session owns the selected model
        elif self.provider == "litellm":
            api_key = config.LITELLM_API_KEY
            base_url = config.LITELLM_BASE_URL
            effective_model = self.model
        else:
            api_key = config.OPENAI_API_KEY
            base_url = config.OPENAI_BASE_URL
            effective_model = self.model

        if not api_key:
            missing = "LLM_API_KEY/LLM_GATEWAY_URL" if gateway_url else ("LITELLM_API_KEY" if self.provider == "litellm" else "OPENAI_API_KEY")
            raise RuntimeError(f"{missing} is not configured.")

        if schema:
            response_format = {
                "type": "json_schema",
                "json_schema": {
                    "name": "quotation_intelligence_response",
                    "strict": True,
                    "schema": schema,
                },
            }
        else:
            response_format = {"type": "json_object"}

        payload = {
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "temperature": temperature,
            "response_format": response_format,
        }
        r = requests.post(
            f"{base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
            timeout=config.REQUEST_TIMEOUT,
        )
        if r.status_code == 401 and gateway_token:
            try:
                detail = r.json().get("detail") or r.json().get("error", {}).get("message") or r.text
            except Exception:
                detail = r.text
            raise RuntimeError(f"Portfolio LLM Gateway rejected the session: {detail}")
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]

    def _gemini(self, prompt: str, system: str, temperature: float,
                schema: Optional[Dict[str, Any]]) -> str:
        if not config.GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY is not configured.")

        candidates = [config.GEMINI_MODEL, *config.GEMINI_FALLBACK_MODELS]
        seen = set()
        last_404 = None
        for model in candidates:
            if not model or model in seen:
                continue
            seen.add(model)
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            generation_config = {
                "temperature": temperature,
                "responseMimeType": "application/json",
            }
            compatible_schema = _gemini_compatible_schema(schema)
            if compatible_schema:
                generation_config["responseSchema"] = compatible_schema

            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": generation_config,
            }
            if system:
                payload["systemInstruction"] = {"parts": [{"text": system}]}

            r = requests.post(
                url,
                headers={"x-goog-api-key": config.GEMINI_API_KEY},
                json=payload,
                timeout=config.REQUEST_TIMEOUT,
            )
            if r.status_code == 404:
                last_404 = r
                logger.warning("Gemini model %s is unavailable; trying the next configured model.", model)
                continue
            if r.status_code >= 400:
                try:
                    detail = r.json().get("error", {}).get("message", r.text)
                except ValueError:
                    detail = r.text
                raise RuntimeError(f"Gemini request failed ({r.status_code}): {detail}")
            data = r.json()
            candidates_out = data.get("candidates") or []
            if not candidates_out:
                raise RuntimeError("Gemini returned no candidates.")
            parts = candidates_out[0].get("content", {}).get("parts", [])
            text = "".join(part.get("text", "") for part in parts if isinstance(part, dict))
            if not text:
                raise RuntimeError("Gemini returned an empty text response.")
            self._active_gemini_model = model
            return text

        raise RuntimeError(
            "No configured Gemini model is available. "
            f"Tried: {', '.join(seen)}. Set GEMINI_MODEL to a currently available model."
        ) from last_404

    def health(self) -> Dict[str, Any]:
        if self.use_gateway:
            return {
                "provider": "gateway",
                "model": self.model,
                "available": True,
                "gateway": self.gateway_url,
            }
        if self.provider == "ollama":
            try:
                r = requests.get(f"{config.OLLAMA_BASE_URL.rstrip('/')}/api/tags", timeout=5)
                r.raise_for_status()
                names = [m.get("name", "") for m in r.json().get("models", [])]
                return {"provider": "ollama", "model": self.model, "available": self.model in names, "models": names}
            except Exception as exc:
                return {"provider": "ollama", "model": self.model, "available": False, "error": str(exc)}
        if self.provider == "litellm":
            # LITELLM_BASE_URL is the OpenAI-compatible API root (/v1).
            # LiteLLM's liveness endpoint lives one level above /v1.
            base_url = config.LITELLM_BASE_URL.rstrip("/")
            gateway_url = base_url[:-3] if base_url.endswith("/v1") else base_url
            try:
                r = requests.get(f"{gateway_url}/health/liveliness", timeout=5)
                r.raise_for_status()
                return {
                    "provider": "litellm",
                    "model": self.model,
                    "available": True,
                    "gateway": gateway_url,
                }
            except Exception as exc:
                return {
                    "provider": "litellm",
                    "model": self.model,
                    "available": False,
                    "gateway": gateway_url,
                    "error": str(exc),
                }
        key = config.OPENAI_API_KEY if self.provider == "openai" else config.GEMINI_API_KEY
        return {"provider": self.provider, "model": self.model, "available": bool(key)}
