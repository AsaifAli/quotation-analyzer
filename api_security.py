"""Bearer-token authentication for the QuoteSense API."""

import hmac

from fastapi import Header, HTTPException

import config


def api_auth_error(authorization: str | None):
    """Return an HTTP error tuple, or None when authentication succeeds."""
    expected = config.API_AUTH_TOKEN

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
):
    """FastAPI route dependency providing defense-in-depth authentication."""
    error = api_auth_error(authorization)

    if error:
        status, detail = error
        headers = {"WWW-Authenticate": "Bearer"} if status == 401 else {}
        raise HTTPException(
            status_code=status,
            detail=detail,
            headers=headers,
        )