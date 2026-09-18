"""Source transformations persisted as notebook insights."""

from __future__ import annotations

import datetime as dt
import os
import uuid

from context_builder import build_context
from phase3_common import FriendlyGeminiError, generate_gemini_text
from storage import STORE

TRANSFORMATION_PROMPTS = {
    "summary": "Create a concise factual summary of the source. Use only information present in the supplied source context.",
    "key_points": "Extract the most important facts, concepts, definitions, and relationships from the supplied source. Do not add outside facts.",
    "key_concepts": "Extract and explain the most important concepts and how they relate. Do not add outside facts.",
    "faq": "Create a source-grounded FAQ with concise questions and answers. Every answer must be supported by the source.",
    "outline": "Turn the source into a hierarchical outline that preserves its major structure and supporting points.",
    "glossary": "Create a glossary of important terms and definitions found in the source. Do not add outside definitions.",
    "quiz": "Create a short quiz with questions and answers supported by the source. Include a mix of recall and understanding questions.",
    "study_guide": "Turn the supplied source into a structured study guide with definitions, mechanisms, and exam-relevant points. Use only the source.",
    "flashcards": "Create concise question-answer flashcards from the supplied source. Every answer must be supported by the source context.",
    "timeline": "Extract chronological events or stages from the source. If the source is not chronological, say so instead of inventing dates.",
    "compare_contrast": "Compare the major concepts, entities, methods, or positions explicitly present in the source. Do not invent a comparison target.",
    "explain_simply": "Explain the source's main ideas in simple language suitable for a beginner while preserving factual meaning.",
    "misconceptions": "Identify likely misconceptions a learner could make from the source and correct them using only the source evidence.",
}


def _now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def _generate(prompt: str) -> tuple[str, str]:
    try:
        text, model, _ = generate_gemini_text(
            prompt,
            system_instruction=(
                "You are Apollo's source transformation engine. Use only the supplied source content. "
                "Never invent details or rely on outside knowledge. If evidence is insufficient, explicitly say so."
            ),
            output_tokens=2200,
            primary_model=os.getenv("APOLLO_TRANSFORM_MODEL", os.getenv("APOLLO_WEB_SYNTHESIS_MODEL")),
            max_models=3,
            retry_primary_once=True,
            request_timeout_ms=int(os.getenv("APOLLO_TRANSFORM_GEMINI_TIMEOUT_MS", "12000")),
        )
        return text, model
    except FriendlyGeminiError:
        raise


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
    if not built.get("context"):
        raise ValueError("Source has no indexed content")
    prompt = (
        "TASK: " + instruction + "\n"
        f"SOURCE ({source_name}):\n{built['context']}"
    )
    content, model = _generate(prompt)
    if not content:
        raise RuntimeError("Transformation returned empty content")

    record = {
        "id": "ins_" + uuid.uuid4().hex[:12],
        "notebook_id": notebook_id,
        "source_name": source_name,
        "insight_type": transformation_type,
        "content": content,
        "model_used": model,
        "status": "completed",
        "error": None,
        "created": _now(),
        "updated": _now(),
    }
    if STORE:
        return STORE.create_insight(record)
    return record
