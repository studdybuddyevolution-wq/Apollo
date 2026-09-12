from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from groq import Groq
from pydantic import BaseModel, Field

from rag_service import add_source, create_notebook, delete_notebook, format_context, get_notebook, list_notebooks, list_sources, remove_source, rename_notebook, retrieve
from research_engine import build_synthesis_instruction, format_evidence, is_detailed_request, run_hybrid_research

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

app = FastAPI(title="Apollo API", version="0.8.0")
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


def _event(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _load_overview_context(notebook_id: str, source_names: list[str], max_chunks: int = 6) -> tuple[str, list[str]]:
    data_dir = Path(os.getenv("APOLLO_DATA_DIR", Path(__file__).resolve().parent / "data"))
    path = data_dir / "notebooks" / notebook_id / "chunks.json"
    if not path.exists():
        return "", source_names
    try:
        chunks = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return "", source_names
    allowed = set(source_names or [])
    filtered = [c for c in chunks if not allowed or c.get("source") in allowed]
    if not filtered:
        return "", source_names
    selected, seen = [], set()
    for chunk in filtered:
        src = chunk.get("source", "unknown source")
        if src not in seen:
            selected.append(chunk)
            seen.add(src)
            if len(selected) >= max_chunks:
                break
    selected_ids = {c.get("id") for c in selected}
    for chunk in filtered:
        if len(selected) >= max_chunks:
            break
        if chunk.get("id") not in selected_ids:
            selected.append(chunk)
    context = format_context([{"source": c.get("source", "unknown source"), "text": c.get("text", ""), "score": 0.0} for c in selected], max_chars=9000)
    return context, list(dict.fromkeys(c.get("source", "unknown source") for c in selected))


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
    if request.web_enabled and request.research_mode == "web":
        content += (
            " Live web research is enabled. Web results are supplied by Tavily. Use them as evidence and synthesize a direct answer. "
            "Do not paste search results or use Markdown tables, raw HTML, <br>, or internal citation markers. Prefer authoritative sources."
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


def _stream_gemini_resilient(*, prompt: str, system_instruction: str, output_tokens: int, primary_model: str, event_meta: dict[str, Any]):
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not configured")
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=key)
    models = _gemini_model_chain(primary_model)
    last_error = None
    for index, model in enumerate(models):
        emitted = False
        try:
            stream = client.models.generate_content_stream(model=model, contents=prompt, config=types.GenerateContentConfig(max_output_tokens=output_tokens, system_instruction=system_instruction))
            yield _event({"type": "start", "model": model, **event_meta})
            for chunk in stream:
                text = getattr(chunk, "text", None) or ""
                if text:
                    emitted = True
                    yield _event({"type": "token", "text": text})
            yield _event({"type": "done", "model": model, **event_meta})
            return
        except Exception as exc:
            last_error = exc
            if emitted:
                yield _event({"type": "error", "message": f"Gemini {model} stream failed after output: {exc}"})
                return
            if index < len(models) - 1:
                yield _event({"type": "fallback", "from_model": model, "to_model": models[index + 1], "reason": str(exc)})
                continue
            break
    raise RuntimeError(f"All Gemini synthesis models failed: {last_error}")


def _stream_deep_research(request: ChatRequest, system_content: str, context: str, source_names: list[str]):
    question = next((m.content for m in reversed(request.messages) if m.role == "user"), "").strip()
    if not question:
        raise RuntimeError("No user query supplied for Deep Research")
    plan = run_hybrid_research(question=question, user_id=request.user_id, notebook_id=request.notebook_id, source_names=source_names, study=request.research_mode == "study")
    instruction = build_synthesis_instruction(topic=plan["topic"], outline=plan["outline"], verification=plan["verification"], requested_detail=is_detailed_request(question), study=request.research_mode == "study")
    evidence = format_evidence(plan["evidence"])
    notebook_context = f"\n\nLEGACY ACTIVE NOTEBOOK CONTEXT:\n{context}" if context else ""
    prompt = _conversation_text(request.messages, instruction) + "\n\nRESEARCH PLAN:\n" + json.dumps(plan["plan"], ensure_ascii=False, indent=2) + "\n\nVERIFIED EVIDENCE:\n" + evidence + notebook_context
    if plan["web_sources"]:
        yield _event({"type": "sources", "sources": plan["web_sources"]})
    yield from _stream_gemini_resilient(prompt=prompt, system_instruction=instruction, output_tokens=DEEP_OUTPUT_TOKENS, primary_model=WEB_SYNTHESIS_MODEL, event_meta={"provider": "gemini+hybrid-rag+tavily", "web": True, "deep": True, "research": request.research_mode, "topic": plan["topic"], "evidence": {k: plan["verification"][k] for k in ("web_sources", "notebook_chunks", "high_authority_sources")}})


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
    for item in response.get("results", []) or []:
        url = str(item.get("url") or "").strip()
        title = str(item.get("title") or url).strip()
        text = str(item.get("raw_content") or item.get("content") or "").strip()
        if url and url not in seen:
            sources.append({"title": title[:180], "url": url})
            seen.add(url)
        if text:
            blocks.append(f"SOURCE: {title}\nURL: {url}\n{text[:6000]}")
    if not blocks:
        raise RuntimeError("Tavily returned no usable web results")
    instruction = system_content + "\n\nYou are Apollo's web-answer synthesizer. Write the answer from the Tavily evidence. Do not paste snippets. Prefer authoritative sources. Use clean Markdown and finish naturally."
    prompt = _conversation_text(request.messages, instruction) + "\n\nTAVILY RESEARCH DOSSIER:\n" + "\n\n---\n\n".join(blocks)
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
            if last_user_message:
                results = retrieve(request.user_id, request.notebook_id, last_user_message, top_k=5, source_names=active_source_names)
                context = format_context(results)
                if results:
                    active_source_names = list(dict.fromkeys(result["source"] for result in results))
                else:
                    context, overview_sources = _load_overview_context(request.notebook_id, active_source_names)
                    if overview_sources:
                        active_source_names = overview_sources
        yield from _stream_model(request, context, active_source_names)
    except Exception as exc:
        yield _event({"type": "error", "message": str(exc)})


@app.get("/api/health")
def health() -> dict[str, object]:
    return {"status": "ok", "service": "apollo-api", "version": "0.8.0", "groq_configured": bool(os.getenv("GROQ_API_KEY", "").strip()), "gemini_configured": bool(os.getenv("GEMINI_API_KEY", "").strip()), "tavily_configured": bool(os.getenv("TAVILY_API_KEY", "").strip()), "primary_model": PRIMARY_MODEL, "vision_model": GROQ_VISION_MODEL, "fallback_model": GEMINI_FALLBACK_MODEL, "gemini_fallback_chain": GEMINI_FALLBACK_MODELS, "deep_output_tokens": DEEP_OUTPUT_TOKENS, "deep_research": "hybrid_rag_tavily", "web_search": "tavily"}


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
async def notebook_source_upload(notebook_id: str, file: UploadFile = File(...), user_id: str = Query("default")):
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    try:
        return add_source(user_id, notebook_id, file.filename or "source.txt", raw)
    except KeyError:
        raise HTTPException(status_code=404, detail="Notebook not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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


@app.post("/api/chat")
def chat(request: ChatRequest) -> StreamingResponse:
    return StreamingResponse(_stream_chat(request), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no-cache"})
