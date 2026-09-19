"""Error classification for AI provider errors.

Adapted from open-notebook (github.com/lfnovo/open-notebook, MIT License,
Copyright (c) 2024 Luis Novo), simplified for Apollo: no custom exception
hierarchy and stdlib logging only.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("apollo.errors")

# Each rule: (keywords to match in the lowercased error text, HTTP status to
# use, user-facing message -- None means pass through the original message).
_CLASSIFICATION_RULES: list[tuple[list[str], int, str | None]] = [
    (
        ["authentication", "unauthorized", "invalid api key", "invalid_api_key", "401"],
        401,
        "Authentication with the AI provider failed. Please check the configured API key.",
    ),
    (
        ["rate limit", "rate_limit", "429", "too many requests", "quota exceeded"],
        429,
        "Rate limit exceeded. Please wait a moment and try again.",
    ),
    (
        ["model not found", "does not exist", "model_not_found"],
        400,
        None,
    ),
    (
        ["connecterror", "timeoutexception", "connection refused", "connection error", "timed out", "timeout"],
        504,
        "Could not reach the AI provider in time. Please try again.",
    ),
    (
        ["context length", "token limit", "maximum context", "context_length_exceeded", "max_tokens"],
        413,
        "This request is too large for the selected model. Try a shorter question or fewer sources.",
    ),
    (
        ["413", "payload too large", "request entity too large"],
        413,
        "The request payload is too large. Try reducing the content size.",
    ),
    (
        ["500", "502", "503", "service unavailable", "overloaded", "internal server error"],
        502,
        "The AI provider is temporarily unavailable (likely high demand). Please try again shortly.",
    ),
]


def classify_error(exception: BaseException) -> tuple[int, str]:
    """Return (HTTP status code, user-facing message) for an AI/provider error."""
    error_str = str(exception).lower()
    combined = f"{type(exception).__name__.lower()}: {error_str}"
    for keywords, status_code, message in _CLASSIFICATION_RULES:
        for keyword in keywords:
            if keyword in combined:
                return (
                    status_code,
                    message if message is not None else _truncate(str(exception)),
                )

    logger.warning(
        "Unclassified AI provider error (%s): %s",
        type(exception).__name__,
        exception,
    )
    return 502, f"AI service error: {_truncate(str(exception))}"

_SOURCE_PERMANENT_MARKERS = (
    "invalid url",
    "unsupported",
    "no transcript",
    "no readable text",
    "empty source",
    "source not found",
    "client error 400",
    "client error 401",
    "client error 403",
    "client error 404",
    "not found",
)


def classify_source_error(exception: BaseException) -> tuple[bool, int, str]:
    """Return (retryable, status_code, user_message) for source/job failures.

    Value/validation errors and known permanent source failures should surface
    immediately. Provider/network/timeouts and other 5xx-class failures are
    retryable without changing Apollo's existing job architecture.
    """
    explicit_status = getattr(exception, "status_code", None)
    detail = getattr(exception, "detail", None)

    if isinstance(explicit_status, int):
        if explicit_status in {408, 429} or explicit_status >= 500:
            _status, message = classify_error(exception)
            return True, 503 if explicit_status >= 500 else explicit_status, message
        if 400 <= explicit_status < 500:
            return False, explicit_status, str(detail or exception)

    text = str(exception).lower()
    if isinstance(exception, ValueError) or any(marker in text for marker in _SOURCE_PERMANENT_MARKERS):
        return False, 400, _truncate(str(exception))

    status_code, message = classify_error(exception)
    retryable = status_code in {408, 429} or status_code >= 500
    return retryable, (503 if retryable and status_code >= 500 else status_code), message



def _truncate(text: str, max_length: int = 200) -> str:
    return text if len(text) <= max_length else text[:max_length] + "..."
