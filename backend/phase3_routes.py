"""Phase 3 Studio routes built on Marklyf's existing RAG/context stack."""

from __future__ import annotations

import asyncio
import base64
import datetime as dt
import json
import os
import re
import uuid
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from context_builder import build_context
from diagrams import build_diagram_prompt, content_overlap_ratio, generate_and_render
from main import _check_rate_limit
from phase3_common import FriendlyGeminiError, extract_json_object, generate_gemini_text, gemini_model_chain
from rag_service import get_notebook, get_notebook_chunks
from storage import STORE
from transformations import TRANSFORMATION_PROMPTS
from study_report import (
    build_full_report_prompt,
    build_questions_prompt,
    build_report_plan,
    build_section_prompt,
    format_evidence,
    normalize_report_data,
    normalize_section_response,
    render_report_markdown,
    report_grounding_score,
    report_to_docx,
    run_hybrid_research,
)


STUDIO_OUTPUT_TYPES = {"slides", "report", "podcast", "transform", "video"}


class Phase3MindMapRequest(BaseModel):
    active_sources: list[str] = Field(default_factory=list)
    diagram_hint: str | None = None
    user_id: str | None = None


class StudioGenerateRequest(BaseModel):
    tool: Literal["slides", "report", "podcast", "transform", "video"]
    model: str | None = None
    active_sources: list[str] = Field(default_factory=list)
    transformation_type: str | None = None
    custom_prompt: str | None = None
    user_id: str | None = None
    report_mode: Literal["study", "deep", "academic"] = "study"
    report_focus: str | None = None
    requested_sections: list[str] = Field(default_factory=list)


class ReportExportRequest(BaseModel):
    markdown: str = Field(min_length=1, max_length=300_000)
    title: str = Field(default="Marklyf Study Report", min_length=1, max_length=180)


class ReportSectionRequest(BaseModel):
    report_mode: Literal["study", "deep", "academic"] = "study"
    report_focus: str | None = None
    section_heading: str = Field(min_length=2, max_length=160)
    active_sources: list[str] = Field(default_factory=list)
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


def _safe_generation(prompt: str, *, system: str, output_tokens: int, max_models: int = 3, preferred_model: str | None = None) -> tuple[str, str]:
    try:
        configured = gemini_model_chain(max_models=None)
        primary = preferred_model or os.getenv("APOLLO_STUDIO_MODEL", os.getenv("APOLLO_WEB_SYNTHESIS_MODEL"))
        if preferred_model and preferred_model not in configured:
            raise HTTPException(status_code=400, detail="Selected Studio model is not enabled on this Marklyf deployment.")
        text, model, _ = generate_gemini_text(
            prompt,
            system_instruction=system,
            output_tokens=output_tokens,
            primary_model=primary,
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
            "You are Marklyf's notebook diagram generator. Use only the provided notebook source content. "
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
        raise HTTPException(status_code=504, detail="Marklyf's diagram generation timed out before a complete result was available.") from None
    except Exception:
        raise HTTPException(status_code=502, detail="Marklyf could not prepare the diagram renderer response.") from None

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
        raise HTTPException(status_code=502, detail="Marklyf generated diagram content but the diagram renderer could not produce a usable result.")

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
        system = "You create source-grounded academic slide decks for Marklyf. Never invent facts."
        prompt = (
            "Return ONLY valid JSON with keys title and slides. slides must be an array of 5-10 objects with keys "
            "title, bullets, speaker_notes, source_refs. bullets must be concise. source_refs must contain only source names from the allowed list. "
            f"ALLOWED SOURCES: {allowed_sources}\n\nSOURCE CONTEXT:\n{context}"
        )
        return prompt, system, 2600
    if tool == "report":
        system = "You create source-grounded study reports for Marklyf. Never add facts that are not supported by the notebook context."
        prompt = (
            "Return ONLY valid JSON with keys title, summary, sections, exam_questions. sections must be an array of objects with keys "
            "heading, points, source_refs. exam_questions must be an array of short questions and answers grounded in the source. "
            f"ALLOWED SOURCES: {allowed_sources}\n\nSOURCE CONTEXT:\n{context}"
        )
        return prompt, system, 3000
    if tool == "podcast":
        system = "You write a two-speaker educational podcast script grounded strictly in Marklyf notebook sources."
        prompt = (
            "Return ONLY valid JSON with keys title, intro, segments, outro. segments must contain 6-12 objects with keys speaker and text; "
            "speaker must be HOST or EXPERT. Keep the script factual, explanatory, and concise. Include source_refs in segment objects and use only allowed source names. "
            f"ALLOWED SOURCES: {allowed_sources}\n\nSOURCE CONTEXT:\n{context}"
        )
        return prompt, system, 3200
    if tool == "video":
        system = "You design source-grounded educational video storyboards for Marklyf. Never invent facts or visuals that imply unsupported claims."
        prompt = (
            "Return ONLY valid JSON with keys title, duration_seconds, scenes. scenes must be an array of 6-10 objects with keys "
            "timecode, title, narration, visual, on_screen_text, source_refs. Each source_refs entry must be a source name from the allowed list. "
            "The output is a storyboard only; do not claim that a video file was rendered. Keep narration concise and visually actionable. "
            f"ALLOWED SOURCES: {allowed_sources}\n\nSOURCE CONTEXT:\n{context}"
        )
        return prompt, system, 3000
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



def _report_word_count(markdown: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", markdown or "", flags=re.UNICODE))


def _report_reference_count(markdown: str) -> int:
    match = re.search(r"(?m)^## References\s*$([\s\S]*)$", markdown or "")
    if not match:
        return 0
    return sum(1 for line in match.group(1).splitlines() if re.match(r"^\s*(?:[-*]|\d+\.)\s+", line))


def _report_notebook_title(user_id: str | None, notebook_id: str) -> str:
    notebook = get_notebook(user_id, notebook_id) or {}
    return str(notebook.get("title") or "Selected notebook sources").strip()


def _generate_report_section_sync(
    *,
    focus: str,
    mode: str,
    heading: str,
    source_names: list[str],
    context: str,
    evidence: str = "",
) -> tuple[dict[str, Any], str]:
    prompt, system, output_tokens = build_section_prompt(
        focus=focus,
        mode=mode,
        section_heading=heading,
        source_names=source_names,
        context=context,
        evidence=evidence,
    )
    text, model = _safe_generation(prompt, system=system, output_tokens=output_tokens, max_models=3)
    return normalize_section_response(extract_json_object(text), heading, source_names), model


def _generate_full_report_sync(
    *,
    focus: str,
    mode: str,
    plan: list[str],
    source_names: list[str],
    context: str,
    evidence: str = "",
) -> tuple[dict[str, Any], str]:
    prompt, system, output_tokens = build_full_report_prompt(
        focus=focus,
        mode=mode,
        plan=plan,
        source_names=source_names,
        context=context,
        evidence=evidence,
    )
    text, model = _safe_generation(prompt, system=system, output_tokens=output_tokens, max_models=3)
    return normalize_report_data(extract_json_object(text), plan=plan, allowed_sources=source_names), model


def _report_stream_event(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def _stream_study_report(notebook_id: str, request: StudioGenerateRequest):
    try:
        if request.tool != "report":
            raise HTTPException(status_code=400, detail="This endpoint only supports Study Reports.")
        if not request.active_sources:
            raise HTTPException(status_code=400, detail="Select at least one source before generating a Study Report.")

        focus = (request.report_focus or _report_notebook_title(request.user_id, notebook_id)).strip() or "the selected notebook sources"
        yield _report_stream_event({"type": "progress", "stage": "planning", "percentage": 8, "message": "Building an adaptive report outline."})

        context, source_names = await asyncio.to_thread(
            _context_or_400, request.user_id, notebook_id, request.active_sources, token_budget=8500, top_k=26
        )
        plan = build_report_plan(focus, request.report_mode, request.requested_sections)
        yield _report_stream_event({"type": "progress", "stage": "outline", "percentage": 18, "message": "Report outline ready.", "plan": plan})

        evidence = ""
        web_sources: list[dict[str, str]] = []
        if request.report_mode == "deep":
            yield _report_stream_event({"type": "progress", "stage": "research", "percentage": 24, "message": "Running notebook + web evidence passes."})
            research = await asyncio.to_thread(
                run_hybrid_research,
                question=focus,
                user_id=request.user_id,
                notebook_id=notebook_id,
                source_names=request.active_sources,
                study=True,
                deep=True,
            )
            evidence = format_evidence(research.get("evidence") or [], max_chars=42000)
            web_sources = research.get("web_sources") or []
            yield _report_stream_event({
                "type": "progress",
                "stage": "research_complete",
                "percentage": 30,
                "message": f"Collected {len(web_sources)} web references alongside notebook evidence.",
            })

        if request.report_mode == "deep":
            sections: list[dict[str, Any]] = []
            models: list[str] = []
            total = len(plan)
            for index, heading in enumerate(plan, 1):
                yield _report_stream_event({
                    "type": "progress",
                    "stage": "section",
                    "percentage": 30 + int(((index - 1) / max(total, 1)) * 48),
                    "current": index,
                    "total": total,
                    "section": heading,
                    "message": f"Generating {heading}.",
                })
                section, model = await asyncio.to_thread(
                    _generate_report_section_sync,
                    focus=focus,
                    mode=request.report_mode,
                    heading=heading,
                    source_names=source_names,
                    context=context,
                    evidence=evidence,
                )
                sections.append(section)
                models.append(model)
                yield _report_stream_event({
                    "type": "progress",
                    "stage": "section_complete",
                    "percentage": 30 + int((index / max(total, 1)) * 48),
                    "current": index,
                    "total": total,
                    "section": heading,
                    "message": f"{heading} complete.",
                })

            questions_prompt, questions_system, questions_tokens = build_questions_prompt(focus, sections)
            yield _report_stream_event({"type": "progress", "stage": "assessment", "percentage": 82, "message": "Building key terms and practice questions."})
            question_text, question_model = await asyncio.to_thread(
                _safe_generation,
                questions_prompt,
                system=questions_system,
                output_tokens=questions_tokens,
                max_models=3,
            )
            question_data = extract_json_object(question_text)
            data = normalize_report_data(
                {
                    "title": f"Deep Study Report: {focus[:120]}",
                    "summary": str(question_data.get("summary") or ""),
                    "sections": sections,
                    "key_terms": [term for section in sections for term in (section.get("key_terms") or [])][:12],
                    "exam_takeaways": [item for section in sections for item in (section.get("exam_takeaways") or [])][:10],
                    "exam_questions": question_data.get("exam_questions") or [],
                },
                plan=plan,
                allowed_sources=source_names,
            )
            models.append(question_model)
        else:
            yield _report_stream_event({"type": "progress", "stage": "generation", "percentage": 32, "message": "Writing the report from the selected sources."})
            data, model_used = await asyncio.to_thread(
                _generate_full_report_sync,
                focus=focus,
                mode=request.report_mode,
                plan=plan,
                source_names=source_names,
                context=context,
                evidence=evidence,
            )
            models = [model_used]
            yield _report_stream_event({"type": "progress", "stage": "generation_complete", "percentage": 82, "message": "Report draft complete."})

        yield _report_stream_event({"type": "progress", "stage": "grounding", "percentage": 90, "message": "Checking source overlap and finalizing references."})
        markdown = render_report_markdown(data, source_names=source_names, web_sources=web_sources)
        overlap = report_grounding_score(markdown, context)

        if overlap < 0.5 and request.report_mode != "deep":
            stricter_prompt, stricter_system, stricter_tokens = build_full_report_prompt(
                focus=focus, mode=request.report_mode, plan=plan, source_names=source_names, context=context, evidence=evidence
            )
            stricter_prompt += "\n\nREGENERATION RULE: The previous draft had weak source overlap. Rewrite it using only claims explicitly supported by the supplied source context. Prefer omission over invention."
            try:
                retry_text, retry_model = await asyncio.to_thread(
                    _safe_generation,
                    stricter_prompt,
                    system=stricter_system,
                    output_tokens=stricter_tokens,
                    max_models=3,
                )
                retry_data = normalize_report_data(extract_json_object(retry_text), plan=plan, allowed_sources=source_names)
                retry_markdown = render_report_markdown(retry_data, source_names=source_names, web_sources=web_sources)
                retry_overlap = report_grounding_score(retry_markdown, context)
                if retry_overlap > overlap:
                    data, markdown, overlap = retry_data, retry_markdown, retry_overlap
                    models.append(retry_model)
            except Exception:
                pass

        models = list(dict.fromkeys(models))
        model_used = models[-1] if models else "Gemini"
        insight = await asyncio.to_thread(_persist_output, notebook_id, "study_report", markdown, model_used)

        result = {
            "tool": "report",
            "data": data,
            "markdown": markdown,
            "insight": insight,
            "model_used": model_used,
            "models_used": models,
            "sources": source_names,
            "web_sources": web_sources,
            "verified": overlap >= 0.5,
            "overlap_ratio": overlap,
            "warning": None if overlap >= 0.5 else "Some report content may not be fully supported by the selected source context. Review it before relying on it.",
            "mode": request.report_mode,
            "plan": plan,
            "word_count": _report_word_count(markdown),
            "reference_count": _report_reference_count(markdown),
        }
        yield _report_stream_event({"type": "progress", "stage": "complete", "percentage": 100, "message": "Study Report ready."})
        yield _report_stream_event({"type": "done", "result": result})
    except HTTPException as exc:
        yield _report_stream_event({"type": "error", "message": str(exc.detail)})
    except FriendlyGeminiError as exc:
        yield _report_stream_event({"type": "error", "message": str(exc)})
    except Exception:
        yield _report_stream_event({"type": "error", "message": "Marklyf could not complete this Study Report."})

def _podcast_script(data: dict[str, Any]) -> str:
    lines = [f"{data.get('title') or 'Marklyf Audio Overview'}", "", "HOST: " + str(data.get("intro") or "").strip()]
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
        "You are Marklyf's source transformation engine.\n"
        f"TASK: {instruction}\n"
        "Use only the supplied notebook content. Do not add outside knowledge. If evidence is insufficient, explicitly say so.\n"
        f"SELECTED SOURCES: {allowed}\n\nSOURCE CONTEXT:\n{context}"
    )
    return prompt, "You produce precise, source-grounded structured study insights for Marklyf.", 2200


def _studio_generate(request: StudioGenerateRequest, notebook_id: str) -> dict[str, Any]:
    context, source_names = _context_or_400(request.user_id, notebook_id, request.active_sources, token_budget=6500, top_k=22)

    if request.tool == "transform":
        prompt, system, output_tokens = _transform_prompt(
            context,
            source_names,
            request.transformation_type or "",
            request.custom_prompt,
        )
        text, model = _safe_generation(
            prompt,
            system=system,
            output_tokens=output_tokens,
            preferred_model=request.model,
        )
        insight = _persist_output(notebook_id, request.transformation_type or "custom", text, model)
        return {"tool": "transform", "transformation_type": request.transformation_type or "custom", "content": text, "insight": insight, "model_used": model, "sources": source_names}

    prompt, system, output_tokens = _studio_prompt(request.tool, context, source_names)
    text, model = _safe_generation(prompt, system=system, output_tokens=output_tokens)
    try:
        data = extract_json_object(text)
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="Marklyf received an incomplete structured Studio response. Please try again.") from exc

    if request.tool == "report":
        focus = (request.report_focus or _report_notebook_title(request.user_id, notebook_id)).strip()
        plan = build_report_plan(focus, request.report_mode, request.requested_sections)
        data = normalize_report_data(data, plan=plan, allowed_sources=source_names)
        markdown = render_report_markdown(data, source_names=source_names)
        overlap = content_overlap_ratio("text", markdown, context)
        if overlap < 0.5:
            stricter_prompt = prompt + (
                "\n\nYour previous report included claims not supported by the source context. "
                "Regenerate using ONLY facts, figures, and claims present in the supplied source context."
            )
            try:
                retry_text, retry_model = _safe_generation(
                    stricter_prompt,
                    system=system,
                    output_tokens=output_tokens,
                    preferred_model=request.model,
                )
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
            "models_used": [model],
            "sources": source_names,
            "verified": overlap >= 0.5,
            "overlap_ratio": round(overlap, 2),
            "warning": None if overlap >= 0.5 else "Some report content may not be fully supported by the selected source context. Review it before relying on it.",
            "mode": request.report_mode,
            "plan": plan,
            "word_count": _report_word_count(markdown),
            "reference_count": _report_reference_count(markdown),
        }
    if request.tool == "slides":
        slides = data.get("slides") or []
        if not slides:
            raise HTTPException(status_code=502, detail="Marklyf produced an empty slide deck. Please try again.")
        insight = _persist_output(notebook_id, "slide_deck", json.dumps(data, ensure_ascii=False), model)
        return {"tool": "slides", "data": data, "insight": insight, "model_used": model, "sources": source_names}

    if request.tool == "video":
        scenes = data.get("scenes") or []
        if not scenes:
            raise HTTPException(status_code=502, detail="Marklyf produced an empty video storyboard. Please try again.")
        insight = _persist_output(notebook_id, "video_storyboard", json.dumps(data, ensure_ascii=False), model)
        return {"tool": "video", "data": data, "insight": insight, "model_used": model, "sources": source_names}

    script = _podcast_script(data)
    insight = _persist_output(notebook_id, "podcast_script", script, model)
    return {"tool": "podcast", "data": data, "script": script, "insight": insight, "model_used": model, "sources": source_names}


def register(app: FastAPI) -> None:
    @app.post("/api/notebooks/{notebook_id}/studio/report/stream")
    async def studio_report_stream(notebook_id: str, request: StudioGenerateRequest, http_request: Request):
        _enforce_rate_limit(http_request, request.user_id)
        if request.tool != "report":
            raise HTTPException(status_code=400, detail="This endpoint only supports Study Reports.")
        return StreamingResponse(
            _stream_study_report(notebook_id, request),
            media_type="text/event-stream",
            headers={"Cache-Control":"no-cache","Connection":"keep-alive","X-Accel-Buffering":"no-cache"},
        )

    @app.post("/api/notebooks/{notebook_id}/studio/report/section")
    async def studio_report_section(notebook_id: str, request: ReportSectionRequest, http_request: Request):
        _enforce_rate_limit(http_request, request.user_id)
        if not request.active_sources:
            raise HTTPException(status_code=400, detail="Select at least one source before regenerating a report section.")
        focus=(request.report_focus or _report_notebook_title(request.user_id, notebook_id)).strip()
        context, source_names = await asyncio.to_thread(
            _context_or_400, request.user_id, notebook_id, request.active_sources, token_budget=7500, top_k=24
        )
        evidence=""
        if request.report_mode=="deep":
            research=await asyncio.to_thread(
                run_hybrid_research,
                question=focus, user_id=request.user_id, notebook_id=notebook_id,
                source_names=request.active_sources, study=True, deep=True
            )
            evidence=format_evidence(research.get("evidence") or [], max_chars=36000)
        section, model = await asyncio.to_thread(
            _generate_report_section_sync,
            focus=focus, mode=request.report_mode, heading=request.section_heading,
            source_names=source_names, context=context, evidence=evidence
        )
        section_text=str(section.get("content") or "")+"\n"+"\n".join(section.get("points") or [])
        score=report_grounding_score(section_text, context)
        return {"tool":"report_section","section":section,"model_used":model,"verified":score>=0.5,"overlap_ratio":score}

    @app.post("/api/notebooks/{notebook_id}/studio/report/docx")
    async def studio_report_docx(notebook_id: str, request: ReportExportRequest, http_request: Request):
        _enforce_rate_limit(http_request, http_request.client.host if http_request.client else "anonymous")
        document=await asyncio.to_thread(report_to_docx, request.markdown, request.title)
        safe_name=(re.sub(r"[^A-Za-z0-9 _-]","_",request.title).strip() or "Marklyf-Study-Report")[:80]
        return {
            "filename": safe_name+".docx",
            "mime_type":"application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "content_base64":base64.b64encode(document).decode("ascii"),
        }

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
            raise HTTPException(status_code=504, detail="Marklyf's Studio generation timed out before a complete result was available.") from None

    app.state.phase3_studio = True
    app.state.phase3_studio_tools = sorted(STUDIO_OUTPUT_TYPES)
