"""Request-scoped LLM gateway token context."""

from contextvars import ContextVar, Token

_llm_gateway_token: ContextVar[str] = ContextVar(
    "llm_gateway_token",
    default="",
)


def set_llm_gateway_token(token: str) -> Token[str]:
    """Set the gateway token and return the reset token."""
    return _llm_gateway_token.set((token or "").strip())


def get_llm_gateway_token() -> str:
    """Return the gateway token associated with the current context."""
    return _llm_gateway_token.get()


def reset_llm_gateway_token(token: Token[str]) -> None:
    """Restore the previous gateway-token context."""
    _llm_gateway_token.reset(token)