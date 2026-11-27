from __future__ import annotations

import json
import os
import ipaddress
import socket
import re

from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


PROJECT = "quotesense"
TIMEOUT_SECONDS = 8
MAX_RESPONSE_BYTES = 64 * 1024

CODE_PATTERN = re.compile(r"^[A-Za-z0-9_-]{32,128}$")


class GatewayHandoffError(RuntimeError):
    """Safe-to-display gateway handoff error."""


class NoRedirectHandler(HTTPRedirectHandler):
    """Do not forward a one-time code through an HTTP redirect."""

    def redirect_request(
        self, request, response, code, message, headers, new_url
    ):
        return None


def configured_gateway_url() -> str:
    value = os.environ.get(
        "PORTFOLIO_SESSION_GATEWAY_URL", ""
    ).strip()

    if value:
        return value

    try:
        from dotenv import dotenv_values

        env_file = Path(__file__).resolve().parent / ".env"
        values = dotenv_values(env_file)

        return str(
            values.get("PORTFOLIO_SESSION_GATEWAY_URL") or ""
        ).strip()

    except Exception:
        return ""


def validate_gateway_destination(base_url: str) -> None:
    """Only send a one-time credential exchange to a trusted, public Gateway host."""
    try:
        parsed = urlsplit(base_url.strip())
        hostname = parsed.hostname
        port = parsed.port
    except ValueError:
        raise GatewayHandoffError("The portfolio gateway URL is invalid.") from None

    if (
        not hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise GatewayHandoffError("The portfolio gateway URL is invalid.")

    host = hostname.rstrip(".").lower()
    is_production = (
        os.getenv("APP_ENV", "").strip().lower() in {"prod", "production"}
        or os.getenv("RENDER", "").strip().lower() in {"1", "true"}
    )
    local_hosts = {"localhost", "127.0.0.1", "::1"}
    if not is_production and host in local_hosts:
        if parsed.scheme not in {"http", "https"}:
            raise GatewayHandoffError("The local portfolio gateway URL is invalid.")
        return

    if parsed.scheme != "https" or port not in {None, 443}:
        raise GatewayHandoffError("The portfolio gateway must use standard HTTPS.")

    allowed_hosts = {
        value.strip().rstrip(".").lower()
        for value in os.getenv(
            "PORTFOLIO_SESSION_GATEWAY_ALLOWED_HOSTS",
            "portfolio-llm-gateway.onrender.com",
        ).split(",")
        if value.strip()
    }
    if host not in allowed_hosts:
        raise GatewayHandoffError("The portfolio gateway host is not approved.")

    try:
        try:
            address = ipaddress.ip_address(host)
            addresses = [address]
        except ValueError:
            records = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
            addresses = [
                ipaddress.ip_address(record[4][0].split("%", 1)[0])
                for record in records
            ]
    except (OSError, ValueError):
        raise GatewayHandoffError("The portfolio gateway host could not be safely resolved.") from None

    if not addresses or any(not address.is_global for address in addresses):
        raise GatewayHandoffError("The portfolio gateway must resolve only to public addresses.")


def exchange_endpoint(base_url: str) -> str:
    try:
        parsed = urlsplit(base_url.strip())
        hostname = parsed.hostname
        _ = parsed.port

    except ValueError as exc:
        raise GatewayHandoffError(
            "The portfolio gateway URL is invalid."
        ) from exc

    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise GatewayHandoffError(
            "The portfolio gateway URL is invalid."
        )

    path = parsed.path.rstrip("/")

    if path.endswith("/v1"):
        path = path[:-3].rstrip("/")

    return urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            f"{path}/v1/demo/session/exchange",
            "",
            "",
        )
    )


def exchange_handoff_code(
    code: str,
    *,
    project: str = PROJECT,
    gateway_url: str | None = None,
) -> dict[str, Any]:

    code = str(code or "").strip()
    project = str(project or "").strip().lower()

    if not CODE_PATTERN.fullmatch(code):
        raise GatewayHandoffError(
            "The QuoteSense launch code is invalid or incomplete."
        )

    if project != PROJECT:
        raise GatewayHandoffError(
            "The target project identifier is invalid."
        )

    base_url = (
        gateway_url.strip()
        if gateway_url
        else configured_gateway_url()
    )

    if not base_url:
        raise GatewayHandoffError(
            "Portfolio session exchange is not configured."
        )

    validate_gateway_destination(base_url)
    endpoint = exchange_endpoint(base_url)

    body = json.dumps(
        {
            "code": code,
            "project": project,
        }
    ).encode("utf-8")

    request = Request(
        endpoint,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Cache-Control": "no-store",
            "Pragma": "no-cache",
        },
        method="POST",
    )

    try:
        opener = build_opener(NoRedirectHandler())

        with opener.open(
            request,
            timeout=TIMEOUT_SECONDS,
        ) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)

    except HTTPError as exc:
        if exc.code == 401:
            raise GatewayHandoffError(
                "The QuoteSense launch code expired, was already used, "
                "or is invalid. Launch again from the portfolio."
            ) from None

        raise GatewayHandoffError(
            "The gateway could not complete the QuoteSense session exchange."
        ) from None

    except (URLError, TimeoutError, OSError):
        raise GatewayHandoffError(
            "The AI gateway could not be reached. Retry the launch from the portfolio."
        ) from None

    if len(raw) > MAX_RESPONSE_BYTES:
        raise GatewayHandoffError(
            "The gateway returned an invalid session response."
        )

    try:
        payload = json.loads(raw.decode("utf-8"))

    except (UnicodeDecodeError, json.JSONDecodeError):
        raise GatewayHandoffError(
            "The gateway returned an invalid session response."
        ) from None

    if not isinstance(payload, dict):
        raise GatewayHandoffError(
            "The gateway returned an invalid session response."
        )

    token = payload.get("access_token")
    target_project = payload.get("target_project")
    expires_in = payload.get("expires_in")

    if (
        not isinstance(token, str)
        or not token.strip()
        or len(token) > 8192
        or "\n" in token
        or "\r" in token
    ):
        raise GatewayHandoffError(
            "The gateway did not return a valid session."
        )

    if target_project != project:
        raise GatewayHandoffError(
            "The gateway returned a session for an unexpected project."
        )

    if (
        isinstance(expires_in, bool)
        or not isinstance(expires_in, int)
        or not 1 <= expires_in <= 3600
    ):
        raise GatewayHandoffError(
            "The gateway returned an invalid session expiry."
        )

    return {
        "access_token": token,
        "expires_in": expires_in,
        "target_project": target_project,
        "provider": str(payload.get("provider") or ""),
        "model": str(payload.get("model") or ""),
    }


def _gateway_session_endpoint(base_url: str, action: str = "status") -> str:
    if action not in {"status", "revoke"}:
        raise GatewayHandoffError("The gateway session action is invalid.")
    validate_gateway_destination(base_url)
    parsed = urlsplit(base_url.strip())
    path = parsed.path.rstrip("/")
    if path.endswith("/v1"):
        path = path[:-3].rstrip("/")
    return urlunsplit((parsed.scheme, parsed.netloc, f"{path}/v1/demo/session/{action}", "", ""))


def verify_gateway_session(
    token: str,
    *,
    gateway_url: str | None = None,
) -> dict[str, Any]:
    """Verify a short-lived token is active and scoped to QuoteSense."""
    token = str(token or "").strip()
    if not token or len(token) > 8192 or "\n" in token or "\r" in token or any(char.isspace() for char in token):
        raise GatewayHandoffError("The QuoteSense Gateway session is invalid or expired.")
    base_url = (gateway_url or os.environ.get("LLM_GATEWAY_URL", "").strip() or configured_gateway_url()).strip()
    if not base_url:
        raise GatewayHandoffError("Portfolio Gateway session verification is not configured.")
    endpoint = _gateway_session_endpoint(base_url, "status")
    request = Request(
        endpoint,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json", "Cache-Control": "no-store"},
        method="GET",
    )
    try:
        with build_opener(NoRedirectHandler()).open(request, timeout=TIMEOUT_SECONDS) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except HTTPError as exc:
        if exc.code in {401, 403}:
            raise GatewayHandoffError("The QuoteSense Gateway session is invalid, expired, or revoked.") from None
        raise GatewayHandoffError("Gateway session verification is temporarily unavailable.") from None
    except (URLError, TimeoutError, OSError):
        raise GatewayHandoffError("Gateway session verification is temporarily unavailable.") from None
    if len(raw) > MAX_RESPONSE_BYTES:
        raise GatewayHandoffError("The gateway returned an invalid session response.")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise GatewayHandoffError("The gateway returned an invalid session response.") from None
    if not isinstance(payload, dict):
        raise GatewayHandoffError("The gateway returned an invalid session response.")
    if payload.get("active") is not True or payload.get("project") != PROJECT or payload.get("session_project") != "portfolio":
        raise GatewayHandoffError("The Gateway session is not authorized for QuoteSense.")
    owner_scope = payload.get("owner_scope")
    if (
        not isinstance(owner_scope, str)
        or len(owner_scope) != 64
        or any(char not in "0123456789abcdef" for char in owner_scope)
    ):
        raise GatewayHandoffError("The Gateway session does not contain a valid workspace owner scope.")
    try:
        import time
        expires_at = int(payload.get("expires_at"))
    except (TypeError, ValueError):
        raise GatewayHandoffError("The gateway returned an invalid session expiry.") from None
    if expires_at - int(time.time()) < 15:
        raise GatewayHandoffError("The QuoteSense Gateway session is expired or expiring.")
    return {
        "active": True,
        "project": PROJECT,
        "provider": str(payload.get("provider") or "")[:80],
        "model": str(payload.get("model") or "")[:200],
        "expires_at": expires_at,
        "owner_scope": owner_scope,
    }
