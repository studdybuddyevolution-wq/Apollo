from __future__ import annotations

import asyncio
import base64
import json
import os
import threading
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from groq import Groq
from pydantic import BaseModel, Field

from request_limits import RequestBodyLimitMiddleware, get_max_request_body_bytes, get_max_upload_bytes

from context_builder import build_context
from diagrams import build_diagram_prompt, generate_and_render, content_overlap_ratio
from jobs import enqueue_job, enqueue_embedding_job, get_job
from rag_service import add_source, create_notebook, delete_notebook, format_context, get_notebook, get_notebook_chunks, list_notebooks, list_sources, remove_source, rename_notebook, retrieve
from research_engine import build_synthesis_instruction, format_evidence, is_detailed_request, run_hybrid_research
from transformations import run_transformation
from storage import STORE
from error_classifier import classify_error
from phase3_common import FriendlyGeminiError, extract_json_object, generate_gemini_text
from pptx_generator import build_source_grounded_pptx

_REPO_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_REPO_ROOT / ".env", override=False)

PRIMARY_MODEL = os.getenv("APOLLO_PRIMARY_MODEL", "openai/gpt-oss-120b")
GROQ_VISION_MODEL = os.getenv("APOLLO_VISION_MODEL", "qwen/qwen3.6-27b")
GEMINI_FALLBACK_MODEL = os.getenv("APOLLO_GEMINI_FALLBACK_MODEL", "gemini-3.8-flash")
WEB_SYNTHESIS_MODEL = os.getenv("APOLLO_WEB_SYNTHESIS_MODEL", "gemini-3.8-flash")
GEMINI_FALLBACK_MODELS = [m.strip() for m in os.getenv("APOLLO_GEMINI_FALLBACK_MODELS", "gemini-3.8-flash,gemini-3.5-flash,gemini-3.1-flash-lite").split(",") if m.strip()]
MAX_OUTPUT_TOKENS = 1000
DEEP_OUTPUT_TOKENS = 2500
WEB_OUTPUT_TOKENS = 1400
PRODUCTION_WEB_ORIGIN = "https://apollo.studdybuddyevolution.workers.dev"
RATE_LIMIT_MAX = int(os.getenv("APOLLO_RATE_LIMIT_MAX", "20"))
RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("APOLLO_RATE_LIMIT_WINDOW_SECONDS", "600"))
MAX_UPLOAD_BYTES = get_max_upload_bytes()
MAX_REQUEST_BODY_BYTES = get_max_request_body_bytes()
_rate_limit_lock = threading.Lock()
_rate_limit_hits: dict[str, list[float]] = defaultdict(list)


def _check_rate_limit(key: str) -> tuple[bool, int]:
    """Sliding-window limiter. Returns (allowed, retry_after_seconds)."""
    now = time.time()
    with _rate_limit_lock:
        hits = _rate_limit_hits[key]
        cutoff = now - RATE_LIMIT_WINDOW_SECONDS
        while hits and hits[0] < cutoff:
            hits.pop(0)
        if len(hits) >= RATE_LIMIT_MAX:
            retry_after = int(hits[0] + RATE_LIMIT_WINDOW_SECONDS - now) + 1
            return False, max(retry_after, 1)
        hits.append(now)
        return True, 0


app = FastAPI(title="Apollo API", version="0.9.0")
app.add_middleware(RequestBodyLimitMiddleware, max_body_size=MAX_REQUEST_BODY_BYTES)
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in os.getenv("APOLLO_CORS_ORIGINS", f"http://localhost:5173,{PRODUCTION_WEB_ORIGIN}").split(",") if o.strip()], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1)
    model: str | None = None
    notebook_id: str | None = None
    notebook_title: str | None = None
    active_sources: list[str] = Field(default_factory=list)
    user_id: str | None = None
    web_enabled: bool = False
    research_mode: Literal["quick", "web", "deep", "study"] = "quick"


class NotebookCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    user_id: str | None = None


class NotebookRenameRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    user_id: str | None = None


class RAGQueryRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=10)
    source_names: list[str] = Field(default_factory=list)
    user_id: str | None = None


class PortfolioDiagramRequest(BaseModel):
    content: str = Field(min_length=1)
    diagram_hint: str | None = None
    user_id: str | None = None


class MindMapRequest(BaseModel):
    active_sources: list[str] = Field(default_factory=list)
    diagram_hint: str | None = None
    user_id: str | None = None


class SlideDeckRequest(BaseModel):
    active_sources: list[str] = Field(default_factory=list)
    user_id: str | None = None
    page_count: int = Field(default=8, ge=4, le=12)
    aspect_ratio: Literal["16:9", "4:3"] = "16:9"


class InsightRequest(BaseModel):
    insight_type: str = Field(min_length=1, max_length=50)
    user_id: str | None = None


class JobRequest(BaseModel):
    type: Literal["embed_source", "embed_notebook"]
    notebook_id: str = Field(min_length=1)
    source_name: str | None = None
    user_id: str | None = None


def _event(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _system_message(request: ChatRequest, context: str, source_names: list[str]) -> dict[str, str]:
    notebook = request.notebook_title or "the active notebook"
    sources = ", ".join(source_names) if source_names else "no active sources"
    content = (
        "You are Apollo Omni AI, a helpful academic AI companion. "
        f"The current notebook is {notebook}. Available sources: {sources}. "
        "Answer directly and naturally. Keep private chain-of-thought/reasoning hidden; return only the answer, conclusions, and useful explanations. "
        "Use supplied source context when relevant and distinguish it from your own knowledge. "
        "When the user asks what a source is about, summarize supplied source context. "
        "Do not claim to have searched or read a source unless the backend supplied that context."
    )
    if request.research_mode == "quick":
        content += (
            " Use Apollo Quick Search format: answer directly in 1-2 sentences, then use 1-3 inline numeric citations like [1] or [2]. "
            "Do not use headings or bullet lists. Stay under 80 words. If uncertain, state that uncertainty in one line."
        )
    elif request.web_enabled and request.research_mode == "web":
        content += (
            " Use Apollo Medium Search format: begin with a 1-sentence direct answer, then provide 2-4 short paragraphs or bullet points with supporting detail, using inline numeric citations like [1], [2], [3]. "
            "End with one short Key takeaway line. Keep the total response between 150 and 300 words."
        )
    if context:
        content += f"\n\nSOURCE CONTEXT:\n{context}"
    return {"role": "system", "content": content}


def _conversation_text(messages: list[ChatMessage], system_content: str) -> str:
    return "\n\n".join([f"SYSTEM:\n{system_content}"] + [f"{m.role.upper()}:\n{m.content}" for m in messages])


def _stream_groq(request: ChatRequest, messages: list[dict[str, str]], model: str):
    key = os.getenv("GROQ_API_KEY", "").strip()
    if not key:
        raise RuntimeError("GROQ_API_KEY is not configured")
    client = Groq(api_key=key)
    kwargs = {"model": model, "messages": messages, "temperature": 0.3, "max_tokens": MAX_OUTPUT_TOKENS, "stream": True}
    if model.startswith("openai/gpt-oss") or model.startswith("qwen/"):
        kwargs["reasoning_format"] = "hidden"
        if model.startswith("openai/gpt-oss"):
            kwargs["reasoning_effort"] = "medium"
    stream = client.chat.completions.create(**kwargs)
    yield _event({"type": "start", "model": model, "provider": "groq", "web": False, "research": "quick"})
    for chunk in stream:
        text = chunk.choices[0].delta.content or ""
        if text:
            yield _event({"type": "token", "text": text})
    yield _event({"type": "done"})


def _gemini_model_chain(primary: str) -> list[str]:
    return list(dict.fromkeys([primary] + [m for m in GEMINI_FALLBACK_MODELS if m != primary]))


def _generate_gemini_once(prompt: str) -> str:
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not configured")
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=30000))
    response = client.models.generate_content(
        model=WEB_SYNTHESIS_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(max_output_tokens=DEEP_OUTPUT_TOKENS),
    )
    return response.text or ""


def _stream_gemini_resilient(*, prompt: str, system_instruction: str, output_tokens: int, primary_model: str, event_meta: dict[str, Any], min_chars: int = 0):
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not configured")
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=key)
    models = _gemini_model_chain(primary_model)
    last_error = None
    for index, model in enumerate(models):
        is_last = index == len(models) - 1
        try:
            stream = client.models.generate_content_stream(model=model, contents=prompt, config=types.GenerateContentConfig(max_output_tokens=output_tokens, system_instruction=system_instruction))
            yield _event({"type": "start", "model": model, **event_meta})
            generated = ""
            finish_reason = None
            for chunk in stream:
                text = getattr(chunk, "text", None) or ""
                if text:
                    generated += text
                    yield _event({"type": "token", "text": text})
                candidates = getattr(chunk, "candidates", None) or []
                if candidates:
                    candidate_reason = getattr(candidates[0], "finish_reason", None)
                    if candidate_reason is not None:
                        finish_reason = candidate_reason

            reason_name = "" if finish_reason is None else (getattr(finish_reason, "name", None) or str(finish_reason).split(".")[-1]).upper()
            abnormal_finish = bool(reason_name) and reason_name != "STOP"
            short_response = min_chars > 0 and len(generated.strip()) < min_chars
            if abnormal_finish or short_response:
                reasons = []
                if abnormal_finish:
                    reasons.append(f"finish_reason={reason_name}")
                if short_response:
                    reasons.append(f"response_too_short={len(generated.strip())}<{min_chars}")
                reason = "; ".join(reasons)
                last_error = RuntimeError(f"Gemini {model} returned an incomplete response: {reason}")
                if is_last:
                    yield _event({"type": "error", "message": str(last_error)})
                    return
                yield _event({"type": "restart", "from_model": model, "to_model": models[index + 1], "reason": str(last_error)})
                continue

            yield _event({"type": "done", "model": model, **event_meta})
            return
        except Exception as exc:
            last_error = exc
            status_code, message = classify_error(exc)
            if is_last:
                yield _event({"type": "error", "status_code": status_code, "message": message})
                return
            yield _event({"type": "restart", "from_model": model, "to_model": models[index + 1], "reason": message})
            continue
    if last_error is not None:
        _, message = classify_error(last_error)
        raise RuntimeError(message) from last_error
    raise RuntimeError("All Gemini synthesis models failed.")


def _stream_deep_research(request: ChatRequest, system_content: str, context: str, source_names: list[str]):
    question = next((m.content for m in reversed(request.messages) if m.role == "user"), "").strip()
    if not question:
        raise RuntimeError("No user query supplied for Deep Research")
    requested_detail = is_detailed_request(question)
    plan = run_hybrid_research(question=question, user_id=request.user_id, notebook_id=request.notebook_id, source_names=source_names, study=request.research_mode == "study", deep=request.research_mode in ("deep", "study"))
    instruction = build_synthesis_instruction(topic=plan["topic"], outline=plan["outline"], verification=plan["verification"], requested_detail=requested_detail, study=request.research_mode == "study")
    evidence = format_evidence(plan["evidence"])
    notebook_context = f"\n\nNOTEBOOK CONTEXT:\n{context}" if context else ""
    prompt = _conversation_text(request.messages, instruction) + "\n\nRESEARCH PLAN:\n" + json.dumps(plan["plan"], ensure_ascii=False, indent=2) + "\n\nVERIFIED EVIDENCE:\n" + evidence + notebook_context
    if plan["web_sources"]:
        yield _event({"type": "sources", "sources": plan["web_sources"]})
    accumulated: list[str] = []
    min_chars = 1200 if requested_detail else 400
    for event in _stream_gemini_resilient(
        prompt=prompt,
        system_instruction=instruction,
        output_tokens=DEEP_OUTPUT_TOKENS,
        primary_model=WEB_SYNTHESIS_MODEL,
        event_meta={
            "provider": "gemini+hybrid-rag+tavily",
            "web": True,
            "deep": True,
            "research": request.research_mode,
            "topic": plan["topic"],
            "evidence": {k: plan["verification"][k] for k in ("web_sources", "notebook_chunks", "high_authority_sources")},
        },
        min_chars=min_chars,
    ):
        yield event
        if not event.startswith("data: "):
            continue
        try:
            payload = json.loads(event[6:].strip())
        except Exception:
            continue
        if payload.get("type") == "token":
            accumulated.append(payload.get("text") or "")
        elif payload.get("type") == "done":
            full_text = "".join(accumulated)
            grounding_source = evidence + notebook_context
            threshold = float(os.getenv("APOLLO_GROUNDING_MIN_OVERLAP", "0.4"))
            overlap = content_overlap_ratio("text", full_text, grounding_source) if full_text else 1.0
            yield _event({
                "type": "grounding_check",
                "verified": overlap >= threshold,
                "overlap_ratio": round(overlap, 2),
                "warning": None if overlap >= threshold else "Some details in this answer may not be fully supported by the retrieved sources -- please verify before relying on it.",
            })


def _stream_web(request: ChatRequest, system_content: str):
    from tavily import TavilyClient
    question = next((m.content for m in reversed(request.messages) if m.role == "user"), "").strip()
    if not question:
        raise RuntimeError("No user query supplied for web research")
    key = os.getenv("TAVILY_API_KEY", "").strip()
    if not key:
        raise RuntimeError("TAVILY_API_KEY is not configured")
    response = TavilyClient(api_key=key).search(query=question, search_depth="advanced", topic="general", max_results=8, chunks_per_source=2, include_answer=False, include_raw_content=True)
    sources, blocks, seen = [], [], set()
    for index, item in enumerate(response.get("results", []) or [], 1):
        url = str(item.get("url") or "").strip()
        title = str(item.get("title") or url).strip()
        text = str(item.get("raw_content") or item.get("content") or "").strip()
        if url and url not in seen:
            sources.append({"title": title[:180], "url": url, "index": index})
            seen.add(url)
        if text:
            blocks.append(f"SOURCE [{index}]: {title}\nURL: {url}\n{text[:6000]}")
    if not blocks:
        raise RuntimeError("Tavily returned no usable web results")
    instruction = system_content + (
        "\n\nYou are Apollo's Medium Search synthesizer. Follow the Medium Search format exactly: begin with a 1-sentence direct answer; then use 2-4 short paragraphs or bullet points with supporting detail; cite supporting claims inline as [1], [2], [3] using the numbered sources supplied below; finish with a single 'Key takeaway:' line. Keep the entire response between 150 and 300 words. Do not add extra sections."
    )
    prompt = _conversation_text(request.messages, instruction) + "\n\nTAVILY SOURCES:\n" + "\n\n---\n\n".join(blocks)
    if sources:
        yield _event({"type": "sources", "sources": sources[:12]})
    yield from _stream_gemini_resilient(prompt=prompt, system_instruction=instruction, output_tokens=WEB_OUTPUT_TOKENS, primary_model=WEB_SYNTHESIS_MODEL, event_meta={"provider": "gemini+tavily", "web": True, "deep": False, "research": "web"})


def _stream_gemini(request: ChatRequest, system_content: str, model: str):
    prompt = _conversation_text(request.messages, system_content)
    yield from _stream_gemini_resilient(prompt=prompt, system_instruction=system_content, output_tokens=MAX_OUTPUT_TOKENS, primary_model=model, event_meta={"provider": "gemini", "fallback": True, "web": False, "research": "quick"})


def _stream_model(request: ChatRequest, context: str, source_names: list[str]):
    system = _system_message(request, context, source_names)
    messages = [system] + [{"role": message.role, "content": message.content} for message in request.messages]
    if request.research_mode in {"deep", "study"}:
        yield from _stream_deep_research(request, system["content"], context, source_names)
        return
    if request.web_enabled:
        yield from _stream_web(request, system["content"])
        return
    groq_model = request.model or PRIMARY_MODEL
    try:
        yield from _stream_groq(request, messages, groq_model)
    except Exception as primary_exc:
        if not os.getenv("GEMINI_API_KEY", "").strip():
            raise primary_exc
        yield _event({"type": "fallback", "from_model": groq_model, "to_model": GEMINI_FALLBACK_MODEL, "reason": str(primary_exc)})
        yield from _stream_gemini(request, system["content"], GEMINI_FALLBACK_MODEL)


def _stream_chat(request: ChatRequest):
    try:
        active_source_names = list(request.active_sources)
        context = ""
        if request.notebook_id:
            last_user_message = next((message.content for message in reversed(request.messages) if message.role == "user"), "")
            built = build_context(request.user_id, request.notebook_id, active_source_names, last_user_message, token_budget=1800, top_k=8, include_insights=True)
            context = built["context"]
            if built["sources"]:
                active_source_names = built["sources"]
        yield from _stream_model(request, context, active_source_names)
    except Exception as exc:
        status_code, message = classify_error(exc)
        yield _event({"type": "error", "status_code": status_code, "message": message})


@app.get("/api/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "service": "apollo-api",
        "version": "0.9.0",
        "groq_configured": bool(os.getenv("GROQ_API_KEY", "").strip()),
        "gemini_configured": bool(os.getenv("GEMINI_API_KEY", "").strip()),
        "tavily_configured": bool(os.getenv("TAVILY_API_KEY", "").strip()),
        "primary_model": PRIMARY_MODEL,
        "vision_model": GROQ_VISION_MODEL,
        "fallback_model": GEMINI_FALLBACK_MODEL,
        "gemini_fallback_chain": GEMINI_FALLBACK_MODELS,
        "deep_output_tokens": DEEP_OUTPUT_TOKENS,
        "deep_research": "hybrid_rag_tavily",
        "web_search": "tavily",
        "embedding_model": os.getenv("APOLLO_EMBEDDING_MODEL", "gemini-embedding-2"),
        "embedding_dimensions": int(os.getenv("APOLLO_EMBEDDING_DIMENSIONS", "768")),
        "pgvector": bool(STORE and STORE.vector_available()),
        "max_upload_bytes": MAX_UPLOAD_BYTES,
        "max_request_body_bytes": MAX_REQUEST_BODY_BYTES,
        "storage_backend": "postgres" if STORE else "filesystem",
        "durable_storage": bool(STORE),
    }


@app.get("/api/notebooks")
def notebooks(user_id: str = "default"):
    return {"notebooks": list_notebooks(user_id)}


@app.post("/api/notebooks")
def notebook_create(request: NotebookCreateRequest):
    return create_notebook(request.user_id, request.title)


@app.get("/api/notebooks/{notebook_id}")
def notebook_detail(notebook_id: str, user_id: str = "default"):
    notebook = get_notebook(user_id, notebook_id)
    if notebook is None:
        raise HTTPException(status_code=404, detail="Notebook not found")
    return notebook


@app.patch("/api/notebooks/{notebook_id}")
def notebook_rename(notebook_id: str, request: NotebookRenameRequest):
    notebook = rename_notebook(request.user_id, notebook_id, request.title)
    if notebook is None:
        raise HTTPException(status_code=404, detail="Notebook not found")
    return notebook


@app.delete("/api/notebooks/{notebook_id}")
def notebook_delete(notebook_id: str, user_id: str = "default"):
    if not delete_notebook(user_id, notebook_id):
        raise HTTPException(status_code=404, detail="Notebook not found")
    return {"deleted": True, "id": notebook_id}


@app.get("/api/notebooks/{notebook_id}/sources")
def notebook_sources(notebook_id: str, user_id: str = "default"):
    if get_notebook(user_id, notebook_id) is None:
        raise HTTPException(status_code=404, detail="Notebook not found")
    return {"sources": list_sources(user_id, notebook_id)}


@app.post("/api/notebooks/{notebook_id}/sources")
async def notebook_source_upload(notebook_id: str, request: Request, file: UploadFile = File(...), user_id: str = Query("default")):
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_UPLOAD_BYTES + 512 * 1024:
                raise HTTPException(status_code=413, detail=f"Upload is too large. Apollo accepts files up to {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")
        except ValueError:
            pass
    raw = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"Upload is too large. Apollo accepts files up to {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")
    if not raw:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    try:
        result = await asyncio.to_thread(
            add_source,
            user_id,
            notebook_id,
            file.filename or "source.txt",
            raw,
            replace_existing=False,
        )
        embedding_job = await enqueue_embedding_job(notebook_id, user_id, result["name"])
        result["embedding_job"] = embedding_job
        return result
    except KeyError:
        raise HTTPException(status_code=404, detail="Notebook not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        status_code, message = classify_error(exc)
        raise HTTPException(status_code=status_code, detail=message) from exc


@app.delete("/api/notebooks/{notebook_id}/sources/{source_name}")
def notebook_source_delete(notebook_id: str, source_name: str, user_id: str = "default"):
    if get_notebook(user_id, notebook_id) is None:
        raise HTTPException(status_code=404, detail="Notebook not found")
    if not remove_source(user_id, notebook_id, source_name):
        raise HTTPException(status_code=404, detail="Source not found")
    return {"deleted": True, "name": source_name}


@app.post("/api/notebooks/{notebook_id}/search")
def notebook_search(notebook_id: str, request: RAGQueryRequest):
    if get_notebook(request.user_id, notebook_id) is None:
        raise HTTPException(status_code=404, detail="Notebook not found")
    results = retrieve(request.user_id, notebook_id, request.query, top_k=request.top_k, source_names=request.source_names)
    return {"results": results}


@app.post("/api/notebooks/{notebook_id}/mindmap")
async def notebook_mindmap(notebook_id: str, request: MindMapRequest, http_request: Request):
    rate_key = request.user_id or (http_request.client.host if http_request.client else "anonymous")
    allowed, retry_after = _check_rate_limit(rate_key)
    if not allowed:
        raise HTTPException(status_code=429, detail=f"Rate limit exceeded. Try again in {retry_after} seconds.", headers={"Retry-After": str(retry_after)})
    if get_notebook(request.user_id, notebook_id) is None:
        raise HTTPException(status_code=404, detail="Notebook not found")

    # Resolve source content on the server. Client text is never trusted as
    # diagram source material for notebook Mind Maps.
    chunks = get_notebook_chunks(request.user_id, notebook_id, request.active_sources)
    if not chunks:
        raise HTTPException(status_code=400, detail="No indexed source content is available for this notebook. Upload a source and try again.")

    topic = request.diagram_hint or "the main concepts, relationships, events, and structure in these notebook sources"
    built = build_context(request.user_id, notebook_id, request.active_sources, topic, token_budget=4500, top_k=18, include_insights=True)
    student_content = built["context"]
    if not student_content:
        raise HTTPException(status_code=400, detail="No indexed source content is available for this notebook. Upload a source and try again.")

    instruction = (
        "You are formatting a student's indexed OWN notebook sources into a diagram. "
        "Use ONLY ideas, terms, events, facts, and relationships already present in the supplied source content. "
        "Do NOT invent facts, plot points, steps, names, or concepts. Your job is only to structure and label what is already present."
    )
    prompt = build_diagram_prompt(topic, context=student_content) + f"\n\n{instruction}"

    def attempt_sync() -> Any:
        text = _generate_gemini_once(prompt)
        return generate_and_render(text)

    try:
        rendered = await asyncio.wait_for(asyncio.to_thread(attempt_sync), timeout=float(os.getenv("GEMINI_DIAGRAM_TIMEOUT", "45")))
        overlap = content_overlap_ratio(rendered.kind, rendered.source_code, student_content) if rendered else 0.0
        if rendered and overlap < 0.5:
            stricter_prompt = prompt + "\n\nYour first attempt introduced labels not supported by the source content. Regenerate using only words and ideas supported by the supplied notebook sources."

            def retry_sync() -> Any:
                text = _generate_gemini_once(stricter_prompt)
                return generate_and_render(text)

            retry = await asyncio.wait_for(asyncio.to_thread(retry_sync), timeout=float(os.getenv("GEMINI_DIAGRAM_RETRY_TIMEOUT", "45")))
            if retry:
                retry_overlap = content_overlap_ratio(retry.kind, retry.source_code, student_content)
                if retry_overlap > overlap:
                    rendered, overlap = retry, retry_overlap
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Diagram generation timed out. Please try again.") from None
    except Exception as exc:
        status_code, message = classify_error(exc)
        raise HTTPException(status_code=status_code, detail=message) from exc

    if not rendered or not rendered.svg_bytes:
        raise HTTPException(status_code=502, detail=rendered.error if rendered else "Diagram generation failed")

    return {
        "kind": rendered.kind,
        "svg": rendered.svg_bytes.decode("utf-8"),
        "verified": overlap >= 0.5,
        "overlap_ratio": round(overlap, 2),
        "warning": None if overlap >= 0.5 else "This diagram may include wording not found in your original content -- please review it before submitting.",
        "sources": list(dict.fromkeys(chunk.get("source") for chunk in chunks if chunk.get("source"))),
    }


@app.post("/api/notebooks/{notebook_id}/studio/slides")
async def notebook_slide_deck(notebook_id: str, request: SlideDeckRequest, http_request: Request):
    rate_key = request.user_id or (http_request.client.host if http_request.client else "anonymous")
    allowed, retry_after = _check_rate_limit(rate_key)
    if not allowed:
        raise HTTPException(status_code=429, detail=f"Rate limit exceeded. Try again in {retry_after} seconds.", headers={"Retry-After": str(retry_after)})
    if get_notebook(request.user_id, notebook_id) is None:
        raise HTTPException(status_code=404, detail="Notebook not found")
    if not request.active_sources:
        raise HTTPException(status_code=400, detail="Select at least one source before generating a slide deck.")

    built = build_context(
        request.user_id,
        notebook_id,
        request.active_sources,
        "create a presentation from the selected notebook sources",
        token_budget=7500,
        top_k=24,
        include_insights=True,
    )
    source_context = built.get("context") or ""
    source_names = built.get("sources") or request.active_sources
    if not source_context:
        raise HTTPException(status_code=400, detail="No indexed source content is available for this notebook.")

    prompt = (
        "Create a source-grounded academic slide deck from ONLY the supplied notebook source context. "
        "Do not invent facts, examples, dates, names, or claims. If the sources do not support a point, omit it. "
        f"Return exactly {request.page_count} slides as JSON with this schema: "
        "{\"title\": string, \"slides\": [{\"title\": string, \"bullets\": [string], \"speaker_notes\": string}]}. "
        "The first slide should be a clear title/overview. Every later slide should have 2-6 concise bullets. "
        "Use a logical teaching sequence and cover the most important source-supported ideas. "
        "Speaker notes should be brief and grounded in the same sources. "
        "\n\nSOURCE CONTEXT:\n" + source_context
    )
    try:
        text, model, _ = await asyncio.to_thread(
            generate_gemini_text,
            prompt,
            system_instruction=(
                "You are Apollo's slide-deck generation engine. Output only valid JSON. "
                "Use only the provided notebook source context and never add outside knowledge."
            ),
            output_tokens=3200,
            primary_model=os.getenv("APOLLO_SLIDE_MODEL", os.getenv("APOLLO_WEB_SYNTHESIS_MODEL")),
            max_models=3,
            retry_primary_once=True,
            request_timeout_ms=int(os.getenv("APOLLO_SLIDE_GEMINI_TIMEOUT_MS", "20000")),
            response_mime_type="application/json",
        )
        payload = extract_json_object(text)
    except FriendlyGeminiError as exc:
        status_code, message = classify_error(exc)
        raise HTTPException(status_code=status_code, detail=message) from exc
    except Exception as exc:
        status_code, message = classify_error(exc)
        raise HTTPException(status_code=status_code, detail=message) from exc

    raw_slides = payload.get("slides") if isinstance(payload, dict) else None
    if not isinstance(raw_slides, list) or not raw_slides:
        raise HTTPException(status_code=502, detail="Apollo's slide generator returned an invalid deck structure.")

    slides = []
    for index, item in enumerate(raw_slides[: request.page_count], 1):
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or f"Slide {index}").strip()
        bullets = [str(value).strip() for value in (item.get("bullets") or []) if str(value).strip()][:6]
        notes = str(item.get("speaker_notes") or "").strip()
        if not bullets:
            bullets = ["No source-supported points were returned for this slide."]
        slides.append({"title": title, "bullets": bullets, "speaker_notes": notes})

    if not slides:
        raise HTTPException(status_code=502, detail="Apollo's slide generator returned no usable slides.")

    try:
        pptx_bytes = build_source_grounded_pptx(
            slides=slides,
            source_names=source_names,
            aspect_ratio=request.aspect_ratio,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"PPTX export failed: {exc}") from exc

    safe_title = str(payload.get("title") or "Apollo Slide Deck").strip() or "Apollo Slide Deck"
    filename = "".join(character if character.isalnum() or character in " -_" else "_" for character in safe_title).strip() or "Apollo Slide Deck"
    filename = f"{filename[:80]}.pptx"
    return {
        "tool": "slides",
        "title": safe_title,
        "slides": slides,
        "source_names": source_names,
        "model_used": model,
        "filename": filename,
        "pptx_base64": base64.b64encode(pptx_bytes).decode("ascii"),
    }


@app.post("/api/notebooks/{notebook_id}/sources/{source_name}/insights")
def notebook_source_insight(notebook_id: str, source_name: str, request: InsightRequest):
    if get_notebook(request.user_id, notebook_id) is None:
        raise HTTPException(status_code=404, detail="Notebook not found")
    if not any(source.get("name") == source_name for source in list_sources(request.user_id, notebook_id)):
        raise HTTPException(status_code=404, detail="Source not found")
    try:
        return run_transformation(request.user_id, notebook_id, source_name, request.insight_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        status_code, message = classify_error(exc)
        raise HTTPException(status_code=status_code, detail=message) from exc


@app.get("/api/notebooks/{notebook_id}/sources/{source_name}/insights")
def notebook_source_insights(notebook_id: str, source_name: str, user_id: str = "default"):
    if get_notebook(user_id, notebook_id) is None:
        raise HTTPException(status_code=404, detail="Notebook not found")
    if not STORE:
        return {"insights": []}
    return {"insights": STORE.list_insights(notebook_id, source_name=source_name)}


@app.post("/api/jobs")
async def create_job(request: JobRequest):
    if get_notebook(request.user_id, request.notebook_id) is None:
        raise HTTPException(status_code=404, detail="Notebook not found")
    try:
        return await enqueue_job(request.type, request.notebook_id, request.user_id, request.source_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/jobs/{job_id}")
def read_job(job_id: str):
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.post("/api/chat")
def chat(request: ChatRequest, http_request: Request) -> StreamingResponse:
    rate_key = request.user_id or (http_request.client.host if http_request.client else "anonymous")
    allowed, retry_after = _check_rate_limit(rate_key)
    if not allowed:
        raise HTTPException(status_code=429, detail=f"Rate limit exceeded. Try again in {retry_after} seconds.", headers={"Retry-After": str(retry_after)})
    return StreamingResponse(_stream_chat(request), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no-cache"})


@app.post("/api/portfolio/diagram")
def portfolio_diagram(request: PortfolioDiagramRequest, http_request: Request):
    rate_key = request.user_id or (http_request.client.host if http_request.client else "anonymous")
    allowed, retry_after = _check_rate_limit(rate_key)
    if not allowed:
        raise HTTPException(status_code=429, detail=f"Rate limit exceeded. Try again in {retry_after} seconds.", headers={"Retry-After": str(retry_after)})

    instruction = (
        "You are formatting a student's OWN work into a diagram. "
        "Use ONLY the ideas, events, and details already present in the "
        "student's content below. Do NOT invent new plot points, facts, "
        "steps, or ideas that are not already there -- your only job is "
        "structuring and labeling what they already wrote."
    )
    topic = request.diagram_hint or "the student's content below"
    prompt = build_diagram_prompt(topic, context=request.content) + f"\n\n{instruction}"

    def _attempt(p: str):
        text = _generate_gemini_once(p)
        return generate_and_render(text)

    try:
        rendered = _attempt(prompt)
    except Exception as exc:
        status_code, message = classify_error(exc)
        raise HTTPException(status_code=status_code, detail=message) from exc
    overlap = content_overlap_ratio(rendered.kind, rendered.source_code, request.content) if rendered else 0.0
    if rendered and overlap < 0.5:
        stricter = prompt + "\n\nYour previous attempt used words not found in the student's own content. Regenerate using ONLY the student's own words and ideas."
        try:
            retry = _attempt(stricter)
        except Exception:
            retry = None
        if retry:
            retry_overlap = content_overlap_ratio(retry.kind, retry.source_code, request.content)
            if retry_overlap > overlap:
                rendered, overlap = retry, retry_overlap

    if not rendered or not rendered.svg_bytes:
        raise HTTPException(status_code=502, detail=rendered.error if rendered else "Diagram generation failed")

    return {
        "kind": rendered.kind,
        "svg": rendered.svg_bytes.decode("utf-8"),
        "verified": overlap >= 0.5,
        "overlap_ratio": round(overlap, 2),
        "warning": None if overlap >= 0.5 else "This diagram may include wording not found in your original content -- please review it before submitting.",
    }
