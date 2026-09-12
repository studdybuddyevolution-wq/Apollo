"""Apollo FastAPI backend.

Phase 5 adds notebook/source/RAG APIs while keeping the streaming chat
endpoint. Model routing is provider-aware: Groq GPT-OSS 120B is the primary
text model, with Gemini 3.8 Flash as an optional fallback. Qwen remains
available as an override for future vision/multimodal requests.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from groq import Groq
from pydantic import BaseModel, Field

from rag_service import (
    add_source,
    create_notebook,
    delete_notebook,
    format_context,
    get_notebook,
    list_notebooks,
    list_sources,
    remove_source,
    rename_notebook,
    retrieve,
)


_REPO_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_REPO_ROOT / ".env", override=False)

PRIMARY_MODEL = os.getenv("APOLLO_PRIMARY_MODEL", "openai/gpt-oss-120b")
GROQ_VISION_MODEL = os.getenv("APOLLO_VISION_MODEL", "qwen/qwen3.6-27b")
GEMINI_FALLBACK_MODEL = os.getenv("APOLLO_GEMINI_FALLBACK_MODEL", "gemini-3.8-flash")
MAX_OUTPUT_TOKENS = 900
PRODUCTION_WEB_ORIGIN = "https://apollo.studdybuddyevolution.workers.dev"


def _cors_origins() -> list[str]:
    raw = os.getenv(
        "APOLLO_CORS_ORIGINS",
        f"http://localhost:5173,{PRODUCTION_WEB_ORIGIN}",
    )
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


app = FastAPI(title="Apollo API", version="0.3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


def _event(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _system_message(request: ChatRequest, context: str, source_names: list[str]) -> dict[str, str]:
    notebook = request.notebook_title or "the active notebook"
    sources = ", ".join(source_names) if source_names else "no active sources"
    content = (
        "You are Apollo Omni AI, a helpful academic AI companion. "
        f"The current notebook is {notebook}. Available sources: {sources}. "
        "Answer directly and naturally. Keep private chain-of-thought/reasoning hidden; "
        "return only the answer, conclusions, and concise useful explanations. "
        "Use supplied source context when it is relevant, and distinguish it from your own knowledge. "
        "Do not claim to have searched or read a source unless the backend supplied that context."
    )
    if context:
        content += f"\n\nSOURCE CONTEXT:\n{context}"
    return {"role": "system", "content": content}


def _conversation_text(messages: list[ChatMessage], system_content: str) -> str:
    lines = [f"SYSTEM:\n{system_content}"]
    for message in messages:
        label = message.role.upper()
        lines.append(f"{label}:\n{message.content}")
    return "\n\n".join(lines)


def _stream_groq(request: ChatRequest, messages: list[dict[str, str]], model: str):
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not configured")

    client = Groq(api_key=api_key)
    kwargs = {
        "model": model,
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": MAX_OUTPUT_TOKENS,
        "stream": True,
    }

    # Groq supports hiding reasoning output for GPT-OSS and Qwen models.
    if model.startswith("openai/gpt-oss") or model.startswith("qwen/"):
        kwargs["reasoning_format"] = "hidden"
        if model.startswith("openai/gpt-oss"):
            kwargs["reasoning_effort"] = "medium"

    stream = client.chat.completions.create(**kwargs)
    yield _event({"type": "start", "model": model, "provider": "groq"})

    for chunk in stream:
        token = chunk.choices[0].delta.content or ""
        if token:
            yield _event({"type": "token", "text": token})

    yield _event({"type": "done"})


def _stream_gemini(request: ChatRequest, system_content: str, model: str):
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured")

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    prompt = _conversation_text(request.messages, system_content)
    stream = client.models.generate_content_stream(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.3,
            max_output_tokens=MAX_OUTPUT_TOKENS,
            system_instruction=system_content,
        ),
    )

    yield _event({"type": "start", "model": model, "provider": "gemini", "fallback": True})
    for chunk in stream:
        text = getattr(chunk, "text", None) or ""
        if text:
            yield _event({"type": "token", "text": text})
    yield _event({"type": "done"})


def _stream_model(request: ChatRequest, context: str, source_names: list[str]):
    system = _system_message(request, context, source_names)
    groq_model = request.model or PRIMARY_MODEL
    messages = [system] + [
        {"role": message.role, "content": message.content}
        for message in request.messages
    ]

    try:
        yield from _stream_groq(request, messages, groq_model)
        return
    except Exception as primary_exc:
        fallback_key = os.getenv("GEMINI_API_KEY", "").strip()
        if not fallback_key:
            raise primary_exc

        yield _event({
            "type": "fallback",
            "from_model": groq_model,
            "to_model": GEMINI_FALLBACK_MODEL,
            "reason": str(primary_exc),
        })
        yield from _stream_gemini(request, system["content"], GEMINI_FALLBACK_MODEL)


def _stream_chat(request: ChatRequest):
    try:
        active_source_names = list(request.active_sources)
        context = ""
        if request.notebook_id:
            last_user_message = next(
                (message.content for message in reversed(request.messages) if message.role == "user"),
                "",
            )
            if last_user_message:
                results = retrieve(
                    request.user_id,
                    request.notebook_id,
                    last_user_message,
                    top_k=5,
                    source_names=active_source_names,
                )
                context = format_context(results)
                if results:
                    active_source_names = list(dict.fromkeys(result["source"] for result in results))

        yield from _stream_model(request, context, active_source_names)
    except Exception as exc:
        yield _event({"type": "error", "message": str(exc)})


@app.get("/api/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "service": "apollo-api",
        "version": "0.3.0",
        "groq_configured": bool(os.getenv("GROQ_API_KEY", "").strip()),
        "gemini_configured": bool(os.getenv("GEMINI_API_KEY", "").strip()),
        "primary_model": PRIMARY_MODEL,
        "vision_model": GROQ_VISION_MODEL,
        "fallback_model": GEMINI_FALLBACK_MODEL,
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
async def notebook_source_upload(
    notebook_id: str,
    file: UploadFile = File(...),
    user_id: str = Form("default"),
):
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
    results = retrieve(
        request.user_id,
        notebook_id,
        request.query,
        top_k=request.top_k,
        source_names=request.source_names,
    )
    return {"results": results}


@app.post("/api/chat")
def chat(request: ChatRequest) -> StreamingResponse:
    return StreamingResponse(
        _stream_chat(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
