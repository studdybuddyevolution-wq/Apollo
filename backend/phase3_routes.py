"""Phase 3 Studio routes built on Apollo's existing RAG/context stack."""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
import uuid
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from context_builder import build_context
from diagrams import build_diagram_prompt, content_overlap_ratio, generate_and_render
from main import _check_rate_limit
from phase3_common import FriendlyGeminiError, extract_json_object, generate_gemini_text, gemini_model_chain
from rag_service import get_notebook, get_notebook_chunks
from storage import STORE
from transformations import TRANSFORMATION_PROMPTS


STUDIO_OUTPUT_TYPES = {"slides", "report", "podcast", "transform"}


class Phase3MindMapRequest(BaseModel):
    active_sources: list[str] = Field(default_factory=list)
    diagram_hint: str | None = None
    user_id: str | None = None


class StudioGenerateRequest(BaseModel):
    tool: Literal["slides", "report", "podcast", "transform"]
    active_sources: list[str] = Field(default_factory=list)
    transformation_type: str | None = None
    custom_prompt: str | None = None
    user_id: str | None = None


def _now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def _enforce_rate_limit(request: Request, user_id: str | None) -> None:
    rate_key = user_id or (request.client.host if request.client else "anonymous")
    allowed, retry_after = _check_rate_limit(rate_key)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Try again in {retry_after} seconds.",
            headers={"Retry-After": str(retry_after)},
        )


def _persist_output(notebook_id: str, insight_type: str, content: str, model_used: str, source_name: str = "__studio__") -> dict[str, Any]:
    record = {
        "id": "ins_" + uuid.uuid4().hex[:12],
        "notebook_id": notebook_id,
        "source_name": source_name,
        "insight_type": insight_type,
        "content": content,
        "model_used": model_used,
        "status": "completed",
        "error": None,
        "created": _now(),
        "updated": _now(),
    }
    return STORE.create_insight(record) if STORE else record


def _context_or_400(user_id: str | None, notebook_id: str, active_sources: list[str], *, token_budget: int, top_k: int) -> tuple[str, list[str]]:
    if get_notebook(user_id, notebook_id) is None:
        raise HTTPException(status_code=404, detail="Notebook not found")
    chunks = get_notebook_chunks(user_id, notebook_id, active_sources)
    if not chunks:
        raise HTTPException(status_code=400, detail="No indexed source content is available for the selected notebook sources.")
    built = build_context(user_id, notebook_id, active_sources, None, token_budget=token_budget, top_k=top_k, include_insights=True)
    context = built.get("context") or ""
    sources = built.get("sources") or active_sources
    if not context:
        raise HTTPException(status_code=400, detail="No usable indexed source context is available for this request.")
    return context, sources


def _safe_generation(prompt: str, *, system: str, output_tokens: int, max_models: int = 3) -> tuple[str, str]:
    try:
        text, model, _ = generate_gemini_text(
            prompt,
            system_instruction=system,
            output_tokens=output_tokens,
            primary_model=os.getenv("APOLLO_STUDIO_MODEL", os.getenv("APOLLO_WEB_SYNTHESIS_MODEL")),
            max_models=max_models,
            retry_primary_once=True,
            request_timeout_ms=int(os.getenv("APOLLO_STUDIO_GEMINI_TIMEOUT_MS", "12000")),
        )
        return text, model
    except FriendlyGeminiError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None


def _mindmap_attempt(prompt: str, context: str, model_chain: list[str]) -> tuple[Any, str]:
    text, model, _ = generate_gemini_text(
        prompt,
        system_instruction=(
            "You are Apollo's notebook diagram generator. Use only the provided notebook source content. "
            "Do not add outside facts, names, events, steps, or concepts."
        ),
        output_tokens=1200,
        primary_model=model_chain[0] if model_chain else None,
        max_models=len(model_chain) or 1,
        retry_primary_once=True,
        request_timeout_ms=int(os.getenv("GEMINI_DIAGRAM_HTTP_TIMEOUT_MS", "12000")),
        model_chain=model_chain or None,
    )
    return generate_and_render(text), model


async def notebook_mindmap_phase3(notebook_id: str, request: Phase3MindMapRequest, http_request: Request):
    _enforce_rate_limit(http_request, request.user_id)
    context, source_names = _context_or_400(request.user_id, notebook_id, request.active_sources, token_budget=4500, top_k=18)
    topic = request.diagram_hint or "the main concepts, relationships, events, and structure in these notebook sources"
    prompt = build_diagram_prompt(topic, context=context) + (
        "\n\nSOURCE-GROUNDING RULES:\n"
        "Use ONLY ideas, terms, events, facts, and relationships already present in the supplied notebook context. "
        "Keep labels concise and source-supported."
    )

    models = gemini_model_chain(os.getenv("APOLLO_STUDIO_MODEL", os.getenv("APOLLO_WEB_SYNTHESIS_MODEL")), max_models=3)
    try:
        rendered, used_model = await asyncio.wait_for(
            asyncio.to_thread(_mindmap_attempt, prompt, context, models),
            timeout=float(os.getenv("GEMINI_DIAGRAM_TIMEOUT", "50")),
        )
    except FriendlyGeminiError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Apollo's diagram generation timed out before a complete result was available.") from None
    except Exception:
        raise HTTPException(status_code=502, detail="Apollo could not prepare the diagram renderer response.") from None

    overlap = content_overlap_ratio(rendered.kind, rendered.source_code, context) if rendered else 0.0
    if rendered and rendered.svg_bytes and overlap < 0.5:
        remaining = [model for model in models if model != used_model][:1]
        if remaining:
            stricter = prompt + "\n\nThe previous diagram contained unsupported labels. Regenerate with only wording and ideas supported by the notebook context."
            try:
                retry_rendered, retry_model = await asyncio.wait_for(
                    asyncio.to_thread(_mindmap_attempt, stricter, context, remaining),
                    timeout=float(os.getenv("GEMINI_DIAGRAM_RETRY_TIMEOUT", "25")),
                )
                retry_overlap = content_overlap_ratio(retry_rendered.kind, retry_rendered.source_code, context) if retry_rendered else 0.0
                if retry_rendered and retry_rendered.svg_bytes and retry_overlap > overlap:
                    rendered, overlap, used_model = retry_rendered, retry_overlap, retry_model
            except Exception:
                pass

    if not rendered or not rendered.svg_bytes:
        raise HTTPException(status_code=502, detail="Apollo generated diagram content but the diagram renderer could not produce a usable result.")

    return {
        "kind": rendered.kind,
        "svg": rendered.svg_bytes.decode("utf-8"),
        "verified": overlap >= 0.5,
        "overlap_ratio": round(overlap, 2),
        "sources": source_names,
        "model_used": used_model,
        "warning": None if overlap >= 0.5 else "Review this diagram: some labels were not found verbatim in the indexed notebook context.",
    }


def _studio_prompt(tool: str, context: str, source_names: list[str]) -> tuple[str, str, int]:
    allowed_sources = ", ".join(source_names) if source_names else "the selected notebook sources"
    if tool == "slides":
        system = "You create source-grounded academic slide decks for Apollo. Never invent facts."
        prompt = (
            "Return ONLY valid JSON with keys title and slides. slides must be an array of 5-10 objects with keys "
            "title, bullets, speaker_notes, source_refs. bullets must be concise. source_refs must contain only source names from the allowed list. "
            f"ALLOWED SOURCES: {allowed_sources}\n\nSOURCE CONTEXT:\n{context}"
        )
        return prompt, system, 2600
    if tool == "report":
        system = "You create source-grounded study reports for Apollo. Never add facts that are not supported by the notebook context."
        prompt = (
            "Return ONLY valid JSON with keys title, summary, sections, exam_questions. sections must be an array of objects with keys "
            "heading, points, source_refs. exam_questions must be an array of short questions and answers grounded in the source. "
            f"ALLOWED SOURCES: {allowed_sources}\n\nSOURCE CONTEXT:\n{context}"
        )
        return prompt, system, 3000
    if tool == "podcast":
        system = "You write a two-speaker educational podcast script grounded strictly in Apollo notebook sources."
        prompt = (
            "Return ONLY valid JSON with keys title, intro, segments, outro. segments must contain 6-12 objects with keys speaker and text; "
            "speaker must be HOST or EXPERT. Keep the script factual, explanatory, and concise. Include source_refs in segment objects and use only allowed source names. "
            f"ALLOWED SOURCES: {allowed_sources}\n\nSOURCE CONTEXT:\n{context}"
        )
        return prompt, system, 3200
    raise ValueError(f"Unsupported Studio tool: {tool}")


def _report_markdown(data: dict[str, Any]) -> str:
    lines = [f"# {data.get('title') or 'Study Report'}", "", str(data.get("summary") or "").strip()]
    for section in data.get("sections") or []:
        lines.extend(["", f"## {section.get('heading') or 'Section'}"])
        lines.extend([f"- {point}" for point in (section.get("points") or [])])
    questions = data.get("exam_questions") or []
    if questions:
        lines.extend(["", "## Practice Questions"])
        for item in questions:
            if isinstance(item, dict):
                lines.append(f"- **Q:** {item.get('question', '')}  ")
                lines.append(f"  **A:** {item.get('answer', '')}")
            else:
                lines.append(f"- {item}")
    return "\n".join(lines).strip()


def _podcast_script(data: dict[str, Any]) -> str:
    lines = [f"{data.get('title') or 'Apollo Audio Overview'}", "", "HOST: " + str(data.get("intro") or "").strip()]
    for segment in data.get("segments") or []:
        lines.extend(["", f"{str(segment.get('speaker') or 'HOST').upper()}: {str(segment.get('text') or '').strip()}"])
    if data.get("outro"):
        lines.extend(["", "HOST: " + str(data.get("outro") or "").strip()])
    return "\n".join(lines).strip()


def _transform_prompt(context: str, source_names: list[str], transformation_type: str, custom_prompt: str | None) -> tuple[str, str, int]:
    instruction = TRANSFORMATION_PROMPTS.get(transformation_type)
    if transformation_type == "custom":
        instruction = custom_prompt.strip() if custom_prompt else None
    if not instruction:
        raise HTTPException(status_code=400, detail="Unsupported or missing transformation type.")
    allowed = ", ".join(source_names) if source_names else "selected notebook sources"
    prompt = (
        "You are Apollo's source transformation engine.\n"
        f"TASK: {instruction}\n"
        "Use only the supplied notebook content. Do not add outside knowledge. If evidence is insufficient, explicitly say so.\n"
        f"SELECTED SOURCES: {allowed}\n\nSOURCE CONTEXT:\n{context}"
    )
    return prompt, "You produce precise, source-grounded structured study insights for Apollo.", 2200


def _studio_generate(request: StudioGenerateRequest, notebook_id: str) -> dict[str, Any]:
    context, source_names = _context_or_400(request.user_id, notebook_id, request.active_sources, token_budget=6500, top_k=22)

    if request.tool == "transform":
        prompt, system, output_tokens = _transform_prompt(
            context,
            source_names,
            request.transformation_type or "",
            request.custom_prompt,
        )
        text, model = _safe_generation(prompt, system=system, output_tokens=output_tokens)
        insight = _persist_output(notebook_id, request.transformation_type or "custom", text, model)
        return {"tool": "transform", "transformation_type": request.transformation_type or "custom", "content": text, "insight": insight, "model_used": model, "sources": source_names}

    prompt, system, output_tokens = _studio_prompt(request.tool, context, source_names)
    text, model = _safe_generation(prompt, system=system, output_tokens=output_tokens)
    try:
        data = extract_json_object(text)
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="Apollo received an incomplete structured Studio response. Please try again.") from exc

    if request.tool == "report":
        markdown = _report_markdown(data)
        overlap = content_overlap_ratio("text", markdown, context)
        if overlap < 0.5:
            stricter_prompt = prompt + "\n\nYour previous report included claims not supported by the source context. Regenerate using ONLY facts, figures, and claims present in the supplied source context."
            try:
                retry_text, retry_model = _safe_generation(stricter_prompt, system=system, output_tokens=output_tokens)
                retry_data = extract_json_object(retry_text)
                retry_markdown = _report_markdown(retry_data)
                retry_overlap = content_overlap_ratio("text", retry_markdown, context)
                if retry_overlap > overlap:
                    data, markdown, overlap, model = retry_data, retry_markdown, retry_overlap, retry_model
            except Exception:
                pass
        insight = _persist_output(notebook_id, "study_report", markdown, model)
        return {
            "tool": "report",
            "data": data,
            "markdown": markdown,
            "insight": insight,
            "model_used": model,
            "sources": source_names,
            "verified": overlap >= 0.5,
            "overlap_ratio": round(overlap, 2),
            "warning": None if overlap >= 0.5 else "Some claims in this report may not be fully supported by the indexed source content -- please review before relying on it.",
        }
    if request.tool == "slides":
        slides = data.get("slides") or []
        if not slides:
            raise HTTPException(status_code=502, detail="Apollo produced an empty slide deck. Please try again.")
        insight = _persist_output(notebook_id, "slide_deck", json.dumps(data, ensure_ascii=False), model)
        return {"tool": "slides", "data": data, "insight": insight, "model_used": model, "sources": source_names}

    script = _podcast_script(data)
    insight = _persist_output(notebook_id, "podcast_script", script, model)
    return {"tool": "podcast", "data": data, "script": script, "insight": insight, "model_used": model, "sources": source_names}


def register(app: FastAPI) -> None:
    path = "/api/notebooks/{notebook_id}/mindmap"
    app.router.routes = [
        route
        for route in app.router.routes
        if not (getattr(route, "path", None) == path and "POST" in getattr(route, "methods", set()))
    ]
    app.add_api_route(path, notebook_mindmap_phase3, methods=["POST"], response_model=dict)

    @app.post("/api/notebooks/{notebook_id}/studio/generate")
    async def studio_generate(notebook_id: str, request: StudioGenerateRequest, http_request: Request):
        _enforce_rate_limit(http_request, request.user_id)
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(_studio_generate, request, notebook_id),
                timeout=float(os.getenv("APOLLO_STUDIO_REQUEST_TIMEOUT", "55")),
            )
        except asyncio.TimeoutError:
            raise HTTPException(status_code=504, detail="Apollo's Studio generation timed out before a complete result was available.") from None

    app.state.phase3_studio = True
    app.state.phase3_studio_tools = sorted(STUDIO_OUTPUT_TYPES)
