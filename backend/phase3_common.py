"""Shared Phase 3 Gemini resilience and structured-output helpers."""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Callable

DEFAULT_GEMINI_MODELS = [
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
]

_TRANSIENT_MARKERS = (
    "503",
    "unavailable",
    "high demand",
    "resource_exhausted",
    "resource exhausted",
    "429",
    "too many requests",
    "rate limit",
    "internal",
    "deadline_exceeded",
    "deadline exceeded",
    "temporarily unavailable",
)


class FriendlyGeminiError(RuntimeError):
    """Exception whose message is safe to show to end users."""

    def __init__(self, message: str, *, transient: bool = False, model: str | None = None):
        super().__init__(message)
        self.transient = transient
        self.model = model


def gemini_model_chain(primary_model: str | None = None, max_models: int | None = None) -> list[str]:
    configured = [
        item.strip()
        for item in os.getenv("APOLLO_GEMINI_FALLBACK_MODELS", ",".join(DEFAULT_GEMINI_MODELS)).split(",")
        if item.strip()
    ]
    primary = (primary_model or os.getenv("APOLLO_WEB_SYNTHESIS_MODEL") or DEFAULT_GEMINI_MODELS[0]).strip()
    models = list(dict.fromkeys([primary] + configured))
    if max_models is not None:
        models = models[: max(1, int(max_models))]
    return models


def is_transient_gemini_error(exc: BaseException) -> bool:
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None) or ""
    text = f"{code} {exc}".lower()
    return any(marker in text for marker in _TRANSIENT_MARKERS)


def _error_is_model_configuration_issue(exc: BaseException) -> bool:
    text = str(exc).lower()
    return any(marker in text for marker in ("not found", "unknown model", "invalid model", "unsupported model"))


def friendly_gemini_error(exc: BaseException, *, transient: bool = False) -> str:
    if transient or is_transient_gemini_error(exc):
        return "Marklyf could not reach a healthy Gemini generation slot after trying its fallback models. Please try again shortly."
    if _error_is_model_configuration_issue(exc):
        return "Marklyf's configured Gemini models are currently unavailable. Check the Gemini model configuration and try again."
    return "Marklyf could not complete this generation with the configured AI service."


def generate_gemini_text(
    prompt: str,
    *,
    system_instruction: str | None = None,
    output_tokens: int = 1800,
    primary_model: str | None = None,
    max_models: int = 3,
    retry_primary_once: bool = True,
    request_timeout_ms: int = 15000,
    response_mime_type: str | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
    client_factory: Callable[[str, int], Any] | None = None,
    model_chain: list[str] | None = None,
) -> tuple[str, str, int]:
    """Generate text with a bounded retry/fallback chain.

    The first model receives at most one exponential-backoff retry for transient
    failures. Later fallback models are tried once each to avoid multiplying token
    cost during provider incidents.
    """
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise FriendlyGeminiError("Gemini is not configured for Marklyf.")

    if client_factory is None:
        from google import genai
        from google.genai import types

        def client_factory(api_key: str, timeout_ms: int):
            return genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=timeout_ms))

    from google.genai import types

    models = list(model_chain or gemini_model_chain(primary_model, max_models=max_models))[: max(1, int(max_models))]
    last_error: BaseException | None = None
    saw_transient = False
    attempts = 0

    for model_index, model in enumerate(models):
        max_attempts = 2 if model_index == 0 and retry_primary_once else 1
        for attempt in range(max_attempts):
            attempts += 1
            try:
                client = client_factory(key, request_timeout_ms)
                config_kwargs: dict[str, Any] = {
                    "max_output_tokens": int(output_tokens),
                    "temperature": 0.2,
                }
                if system_instruction:
                    config_kwargs["system_instruction"] = system_instruction
                if response_mime_type:
                    config_kwargs["response_mime_type"] = response_mime_type
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=types.GenerateContentConfig(**config_kwargs),
                )
                text = (getattr(response, "text", None) or "").strip()
                if not text:
                    raise RuntimeError("Gemini returned an empty response")
                return text, model, attempts
            except Exception as exc:  # provider SDK exceptions vary across releases
                last_error = exc
                transient = is_transient_gemini_error(exc)
                saw_transient = saw_transient or transient
                if transient and attempt + 1 < max_attempts:
                    sleep_fn(0.8 * (2**attempt))
                    continue
                break

    if last_error is None:
        raise FriendlyGeminiError("Marklyf could not complete this generation.")
    raise FriendlyGeminiError(
        friendly_gemini_error(last_error, transient=saw_transient),
        transient=saw_transient,
        model=models[-1] if models else None,
    ) from last_error


def extract_json_object(text: str) -> dict[str, Any]:
    """Parse a JSON object from plain text or a fenced JSON response."""
    value = (text or "").strip()
    if not value:
        raise ValueError("The generation was empty")
    fenced = re.search(r"```(?:json)?\s*(\{[\s\S]*\})\s*```", value, re.IGNORECASE)
    candidate = fenced.group(1) if fenced else value
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start == -1 or end <= start:
            raise ValueError("The AI response was not valid JSON") from None
        parsed = json.loads(candidate[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("The AI response must be a JSON object")
    return parsed
