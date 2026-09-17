"""Lightweight source transformations persisted as notebook insights."""

from __future__ import annotations

import datetime as dt
import os
import uuid

from context_builder import build_context
from storage import STORE

TRANSFORMATION_PROMPTS = {
    "summary": "Create a concise factual summary of the source. Use only information present in the supplied source context.",
    "key_points": "Extract the most important facts, concepts, definitions, and relationships from the supplied source. Do not add outside facts.",
    "study_guide": "Turn the supplied source into a structured study guide with definitions, mechanisms, and exam-relevant points. Use only the source.",
    "flashcards": "Create concise question-answer flashcards from the supplied source. Every answer must be supported by the source context.",
}


def _now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def _generate(prompt: str) -> str:
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not configured")
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=30000))
    model = os.getenv("APOLLO_TRANSFORM_MODEL", os.getenv("APOLLO_WEB_SYNTHESIS_MODEL", "gemini-3.8-flash"))
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(max_output_tokens=1800),
    )
    return (response.text or "").strip()


def run_transformation(
    user_id: str | None,
    notebook_id: str,
    source_name: str,
    transformation_type: str,
) -> dict:
    instruction = TRANSFORMATION_PROMPTS.get(transformation_type)
    if instruction is None:
        raise ValueError(f"Unsupported transformation type: {transformation_type}")
    built = build_context(user_id, notebook_id, [source_name], None, token_budget=4500, top_k=14, include_insights=False)
    if not built["context"]:
        raise ValueError("Source has no indexed content")
    prompt = (
        "You are Apollo's source transformation engine.\n"
        f"TASK: {instruction}\n"
        "Never invent details or rely on outside knowledge. If the source does not contain enough information, say so.\n\n"
        f"SOURCE ({source_name}):\n{built['context']}"
    )
    content = _generate(prompt)
    if not content:
        raise RuntimeError("Transformation returned empty content")

    record = {
        "id": "ins_" + uuid.uuid4().hex[:12],
        "notebook_id": notebook_id,
        "source_name": source_name,
        "insight_type": transformation_type,
        "content": content,
        "model_used": os.getenv("APOLLO_TRANSFORM_MODEL", os.getenv("APOLLO_WEB_SYNTHESIS_MODEL", "gemini-3.8-flash")),
        "status": "completed",
        "error": None,
        "created": _now(),
        "updated": _now(),
    }
    if STORE:
        return STORE.create_insight(record)
    return record
