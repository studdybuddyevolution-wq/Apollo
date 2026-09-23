"""Small HTTP adapter for a self-hosted Presenton instance.

Marklyf owns source selection and grounded slide content. Presenton owns visual
layout, editable PowerPoint export, and its browser editor.
"""

from __future__ import annotations

import os
from pathlib import PurePosixPath
from urllib.parse import urlparse
from typing import Any

import requests


class PresentonError(RuntimeError):
    """Raised when Presenton cannot generate a deck."""


def _base_url() -> str:
    return os.getenv("MARKLYF_PRESENTON_URL", "").strip().rstrip("/")


def is_configured() -> bool:
    url = _base_url()
    if not url or not os.getenv("MARKLYF_PRESENTON_API_KEY", "").strip():
        return False
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    # Marklyf deliberately supports only self-hosted Presenton. The hosted
    # Presenton Cloud service is excluded so this integration cannot silently
    # introduce a paid SaaS dependency.
    if hostname in {"presenton.ai", "www.presenton.ai", "api.presenton.ai", "cloud.presenton.ai"}:
        return False
    return True


def _absolute_link(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip()
    if value.startswith(("http://", "https://")):
        return value
    if value.startswith("/"):
        return f"{_base_url()}{value}"
    return f"{_base_url()}/{value.lstrip('/')}"


def _filename_from_path(path: str | None, fallback: str = "Marklyf-Slide-Deck.pptx") -> str:
    if not path:
        return fallback
    name = PurePosixPath(path.split("?", 1)[0]).name.strip()
    return name or fallback


def _slide_markdown(slide: dict[str, Any]) -> str:
    title = str(slide.get("title") or "Slide").strip()
    bullets = [
        str(value).strip()
        for value in (slide.get("bullets") or [])
        if str(value).strip()
    ]
    lines = [f"# {title}", ""]
    lines.extend(f"- {bullet}" for bullet in bullets[:6])
    return "\n".join(lines).strip()


def generate_deck(
    *,
    slides: list[dict[str, Any]],
    title: str,
    template: str | None = None,
    timeout_seconds: float | None = None,
) -> dict[str, Any]:
    """Generate an editable PPTX through Presenton's API.

    Presenton's \`slides_markdown\` path is used so Marklyf keeps control of
    source-grounded slide content and Presenton handles visual composition/export.
    """

    if not is_configured():
        raise PresentonError(
            "Self-hosted Presenton is not configured. Set MARKLYF_PRESENTON_URL "
            "and MARKLYF_PRESENTON_API_KEY to an owned/self-hosted instance. "
            "Presenton Cloud is not supported by Marklyf."
        )

    if not slides:
        raise PresentonError("No slide content was supplied to Presenton.")

    max_slides = 12
    if len(slides) > max_slides:
        raise PresentonError(f"Presenton integration supports at most {max_slides} slides per request.")

    api_key = os.getenv("MARKLYF_PRESENTON_API_KEY", "").strip()
    timeout = timeout_seconds or float(os.getenv("MARKLYF_PRESENTON_TIMEOUT_SECONDS", "45"))
    template_name = (template or os.getenv("MARKLYF_PRESENTON_TEMPLATE", "general")).strip() or "general"

    payload = {
        "content": "",
        "slides_markdown": [_slide_markdown(slide) for slide in slides],
        "instructions": (
            "Use the supplied slide content as the source of truth. "
            "Do not add factual claims or external examples. "
            "Keep text concise, educational, and presentation-ready. "
            "Prefer a clean visual hierarchy and varied layouts where the template supports them."
        ),
        "tone": "educational",
        "verbosity": "concise",
        "web_search": False,
        "n_slides": len(slides),
        "language": "English",
        "template": template_name,
        "include_table_of_contents": False,
        "include_title_slide": False,
        "export_as": "pptx",
    }

    try:
        response = requests.post(
            f"{_base_url()}/api/v1/ppt/presentation/generate",
            json=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise PresentonError(f"Presenton request failed: {exc}") from exc

    if not response.ok:
        detail = response.text.strip()
        if len(detail) > 500:
            detail = detail[:500] + "…"
        raise PresentonError(
            f"Presenton returned HTTP {response.status_code}"
            + (f": {detail}" if detail else ".")
        )

    try:
        result = response.json()
    except ValueError as exc:
        raise PresentonError("Presenton returned a non-JSON response.") from exc

    presentation_id = result.get("presentation_id")
    pptx_path = result.get("path")
    edit_path = result.get("edit_path")
    if not presentation_id or not pptx_path:
        raise PresentonError("Presenton completed without returning a presentation ID and PPTX path.")

    return {
        "presentation_id": str(presentation_id),
        "pptx_url": _absolute_link(pptx_path),
        "edit_url": _absolute_link(edit_path),
        "filename": _filename_from_path(str(pptx_path)),
        "template": template_name,
    }
