"""Bearer-token authentication for the QuoteSense API."""

import hmac

from fastapi import Header, HTTPException

import config
from gateway_handoff import GatewayHandoffError, verify_gateway_session
from llm_gateway_context import get_llm_gateway_token


def api_auth_error(authorization: str | None, gateway_token: str | None = None):
    """Return an HTTP error tuple, or None when authentication succeeds."""
    expected = config.API_AUTH_TOKEN

    if gateway_token:
        # The request middleware already performed a fresh Gateway status
        # check and placed the identical token in this request's ContextVar.
        # Reuse that scoped verification instead of making a second network
        # call during FastAPI dependency resolution.
        current_token = get_llm_gateway_token()
        if current_token and hmac.compare_digest(current_token, gateway_token):
            return None
        try:
            verify_gateway_session(gateway_token)
            return None
        except GatewayHandoffError as exc:
            message = str(exc).lower()
            if "temporarily unavailable" in message or "not configured" in message:
                return 503, "Gateway session verification is temporarily unavailable."
            return 401, "The project-scoped Gateway session is invalid or expired."

    if not expected:
        return 503, "API authentication is not configured."

    scheme, separator, credential = (authorization or "").partition(" ")

    if (
        scheme.lower() != "bearer"
        or not separator
        or not hmac.compare_digest(credential, expected)
    ):
        return 401, "Authentication required."

    return None


def require_api_auth(
    authorization: str | None = Header(default=None),
    gateway_token: str | None = Header(default=None, alias="X-LLM-Gateway-Token"),
):
    """FastAPI route dependency providing defense-in-depth authentication."""
    error = api_auth_error(authorization, gateway_token)

    if error:
        status, detail = error
        headers = {"WWW-Authenticate": "Bearer"} if status == 401 else {}
        raise HTTPException(
            status_code=status,
            detail=detail,
            headers=headers,
        )