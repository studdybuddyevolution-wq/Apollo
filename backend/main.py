"""Apollo FastAPI backend.

Phase 5 adds notebook/source/RAG APIs while keeping the streaming chat
endpoint. The React frontend can now manage notebooks and upload source files
through this backend instead of relying on Streamlit session state.
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

DEFAULT_MODEL = "qwen/qwen3.6-27b"
MAX_OUTPUT_TOKENS = 900
PRODUCTION_WEB_ORIGIN = "https://apollo.studdybuddyevolution.workers.dev"


def _cors_origins() -> list[str]:
    raw = os.getenv(
        "APOLLO_CORS_ORIGINS",
        f"http://localhost:5173,{PRODUCTION_WEB_ORIGIN}",
    )
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


app = FastAPI(title="Apollo API", version="0.2.0")

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
    model: str = DEFAULT_MODEL
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
        "Use supplied source context when it is relevant, and distinguish it from your own knowledge. "
        "Do not claim to have searched or read a source unless the backend supplied that context."
    )
    if context:
        content += f"\n\nSOURCE CONTEXT:\n{context}"
    return {"role": "system", "content": content}


def _stream_groq(request: ChatRequest):
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        yield _event({
            "type": "error",
            "message": "GROQ_API_KEY is not configured for the FastAPI backend.",
        })
        return

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

        client = Groq(api_key=api_key)
        messages = [_system_message(request, context, active_source_names)] + [
            {"role": message.role, "content": message.content}
            for message in request.messages
        ]

        stream = client.chat.completions.create(
            model=request.model or DEFAULT_MODEL,
            messages=messages,
            temperature=0.3,
            max_tokens=MAX_OUTPUT_TOKENS,
            stream=True,
        )

        yield _event({
            "type": "start",
            "model": request.model or DEFAULT_MODEL,
            "sources": active_source_names,
        })

        for chunk in stream:
            token = chunk.choices[0].delta.content or ""
            if token:
                yield _event({"type": "token", "text": token})

        yield _event({"type": "done"})
    except Exception as exc:
        yield _event({"type": "error", "message": str(exc)})


@app.get("/api/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "service": "apollo-api",
        "version": "0.2.0",
        "groq_configured": bool(os.getenv("GROQ_API_KEY", "").strip()),
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
        _stream_groq(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
