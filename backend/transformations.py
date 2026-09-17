"""Lightweight, persisted source transformations for Apollo Studio."""
from __future__ import annotations

import datetime as dt
import os
import uuid
from typing import Any

from google import genai
from google.genai import types

from rag_service import get_notebook_chunks
from storage import STORE

_TRANSFORMATION_TEMPLATES = {
    "summary": "Create a concise study summary of the supplied source. Preserve the source's facts and terminology; do not invent claims.",
    "key_terms": "Extract the most important terms, names, formulas, definitions, and dates from the supplied source. Give a short explanation for each using only the source.",
    "questions": "Create useful study questions and short answer keys based only on the supplied source.",
    "outline": "Turn the supplied source into a clean hierarchical outline using only its existing ideas and structure.",
}


def _now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def run_transformation(
    user_id: str | None,
    notebook_id: str,
    source_name: str,
    insight_type: str,
) -> dict[str, Any]:
    if insight_type not in _TRANSFORMATION_TEMPLATES:
        raise ValueError(f"Unsupported transformation type: {insight_type}")
    chunks = get_notebook_chunks(user_id, notebook_id, [source_name])
    if not chunks:
        raise KeyError("Source not found")
    content = "\n\n".join(str(chunk.get("text", "")) for chunk in chunks)
    if not content.strip():
        raise ValueError("Source has no readable content")

    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not configured")
    client = genai.Client(
        api_key=key,
        http_options=types.HttpOptions(timeout=int(os.getenv("GEMINI_TRANSFORM_TIMEOUT_MS", "30000"))),
    )
    prompt = (
        f"{_TRANSFORMATION_TEMPLATES[insight_type]}\n\n"
        f"SOURCE: {source_name}\n\n"
        f"SOURCE CONTENT:\n{content[:30000]}"
    )
    response = client.models.generate_content(
        model=os.getenv("APOLLO_WEB_SYNTHESIS_MODEL", "gemini-3.8-flash"),
        contents=prompt,
        config=types.GenerateContentConfig(max_output_tokens=1800),
    )
    output = (response.text or "").strip()
    if not output:
        raise RuntimeError("Transformation returned empty output")

    insight = {
        "id": "ins_" + uuid.uuid4().hex[:12],
        "notebook_id": notebook_id,
        "source_name": source_name,
        "insight_type": insight_type,
        "content": output,
        "model_used": os.getenv("APOLLO_WEB_SYNTHESIS_MODEL", "gemini-3.8-flash"),
        "status": "completed",
        "error": None,
        "created": _now(),
        "updated": _now(),
    }
    if not STORE:
        raise RuntimeError("Source insight persistence requires the Postgres store")
    STORE.create_insight(insight)
    return insight
